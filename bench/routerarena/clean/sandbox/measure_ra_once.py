# SPDX-License-Identifier: MIT
"""Sealed ONE-SHOT RouterArena measurement — the only place real RA data is touched.

The compliance discipline (memory ra-compliance-label-provenance):
  • ALL router refinement happens against the self-generated proxy (grader.py +
    proxy_gen.py). The real RA dataset is a LOCKED test set, touched exactly once
    to produce the submission prediction file — never in a tune→measure→retune loop.

This module enforces that mechanically:
  1. An append-only, hash-CHAINED ledger (`.ra_touch_ledger.jsonl`) records every
     RA touch. Each entry chains to the previous (prev_hash → entry_hash) so a
     touch can't be silently deleted or back-dated.
  2. `assert_first_touch()` REFUSES to run if any completed touch exists, unless
     the operator passes the explicit override phrase — a deliberate, auditable act.
  3. At measurement time the RA evaluator is verified UNMODIFIED (PR-155 rule #2,
     strict) and the exact router source is fingerprinted, so the "measured once,
     with this code, against the unmodified scorer" claim is provable.

Producing predictions is injected (`produce_fn`) so Phase 3 wires the real RA
harness + ChuzomCleanRouter, while the SEAL itself is testable offline.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grader import assert_evaluator_unmodified  # noqa: E402

_HERE = Path(__file__).resolve().parent
_REPO_ROUTER = _HERE.parent  # bench/routerarena/clean/
LEDGER = Path(os.environ.get("CHUZOM_RA_LEDGER", _HERE / ".ra_touch_ledger.jsonl"))
OVERRIDE_PHRASE = "I_UNDERSTAND_THIS_BURNS_THE_ONESHOT"

# Router source files whose exact bytes define "the code used for this touch".
_ROUTER_SOURCES = ["router_core.py", "chuzom_clean_router.py", "calibrate.py"]


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _router_code_fingerprint() -> str:
    h = hashlib.sha256()
    for name in _ROUTER_SOURCES:
        p = _REPO_ROUTER / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"<absent>")
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(_REPO_ROUTER), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        return "unknown"


def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def _completed_touches() -> list[dict]:
    return [e for e in _read_ledger() if e.get("status") == "completed"]


def verify_ledger_chain() -> bool:
    """Recompute the hash chain; return True iff intact (no silent edit/delete)."""
    prev = "GENESIS"
    for e in _read_ledger():
        body = {k: e[k] for k in e if k != "entry_hash"}
        expect = _sha256((prev + json.dumps(body, sort_keys=True)).encode())
        if e.get("entry_hash") != expect:
            return False
        prev = e["entry_hash"]
    return True


def assert_first_touch(override: str | None = None) -> None:
    if not verify_ledger_chain():
        raise RuntimeError(
            f"RA touch ledger {LEDGER} FAILED integrity check — chain broken. "
            "Someone edited/deleted a prior touch. Stop and investigate."
        )
    done = _completed_touches()
    if done and override != OVERRIDE_PHRASE:
        first = done[0]
        raise RuntimeError(
            f"RA already measured (one-shot rule). First touch: {first['utc']} "
            f"score={first.get('score')} code={first.get('router_code_fp','')[:12]}. "
            f"Refusing to re-run. To deliberately burn another one-shot, pass "
            f"override={OVERRIDE_PHRASE!r} — this is an auditable act and should be "
            "justified in the submission PR."
        )


def _append(entry: dict) -> str:
    prev = _read_ledger()
    prev_hash = prev[-1]["entry_hash"] if prev else "GENESIS"
    body = {**entry, "prev_hash": prev_hash}  # hashed body INCLUDES prev_hash
    entry_hash = _sha256((prev_hash + json.dumps(body, sort_keys=True)).encode())
    full = {**body, "entry_hash": entry_hash}
    with LEDGER.open("a") as f:
        f.write(json.dumps(full) + "\n")
    return entry_hash


def measure_once(
    produce_fn: Callable[[], tuple[list[dict], str, dict]],
    *,
    out_path: str | Path = _HERE / "ra_submission_predictions.json",
    override: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the single locked RA measurement.

    produce_fn() -> (predictions, prompt_set_hash, score_dict)
      predictions:     list of RA prediction rows (submission file content)
      prompt_set_hash: hash of the exact RA prompts touched (provenance)
      score_dict:      local metrics (accuracy/arena/...) computed with grader.py

    dry_run=True exercises the seal + evaluator check WITHOUT calling produce_fn
    or recording a completed touch (safe to run any time).
    """
    assert_evaluator_unmodified(strict=True)   # PR-155 rule #2 — refuse on drift
    assert_first_touch(override)

    if dry_run:
        return {"dry_run": True, "ledger_ok": verify_ledger_chain(),
                "prior_touches": len(_completed_touches()),
                "router_code_fp": _router_code_fingerprint(),
                "git_sha": _git_sha()}

    predictions, prompt_set_hash, score = produce_fn()
    out_path = Path(out_path)
    out_path.write_text(json.dumps(predictions, indent=2))
    pred_hash = _sha256(out_path.read_bytes())

    entry = {
        "status": "completed",
        "utc": datetime.now(timezone.utc).isoformat(),
        "n": len(predictions),
        "score": score.get("arena_score"),
        "metrics": score,
        "prompt_set_hash": prompt_set_hash,
        "prediction_file": str(out_path),
        "prediction_file_sha256": pred_hash,
        "router_code_fp": _router_code_fingerprint(),
        "git_sha": _git_sha(),
        "metrics_py_sha256": assert_evaluator_unmodified(strict=True),
    }
    entry_hash = _append(entry)
    return {**entry, "entry_hash": entry_hash}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Sealed one-shot RA measurement.")
    ap.add_argument("--dry-run", action="store_true", help="test the seal; record nothing")
    ap.add_argument("--commit", action="store_true", help="perform the real one-shot")
    ap.add_argument("--override", default=None, help=f"pass {OVERRIDE_PHRASE!r} to burn another one-shot")
    ap.add_argument("--self-test", action="store_true", help="validate seal logic against a temp ledger")
    args = ap.parse_args()

    if args.self_test:
        # Offline validation: mock producer + throwaway ledger. Proves the guard.
        import tempfile
        tmpdir = Path(tempfile.mkdtemp())
        tmp = tmpdir / "ledger.jsonl"
        mock_out = tmpdir / "preds.json"
        os.environ["CHUZOM_RA_LEDGER"] = str(tmp)
        LEDGER = tmp  # noqa: F811

        def mock_produce():
            preds = [{"global index": i, "prediction": "qwen/qwen3-235b-a22b-2507"} for i in range(5)]
            return preds, _sha256(b"mock-prompts"), {"accuracy": 0.75, "arena_score": 0.761}

        print("dry-run (no prior touch):",
              json.dumps({k: v for k, v in measure_once(mock_produce, dry_run=True).items()
                          if k in ("dry_run", "prior_touches", "ledger_ok")}))
        r1 = measure_once(mock_produce, out_path=mock_out)
        print(f"1st commit  → recorded touch, score={r1['score']}, chain_ok={verify_ledger_chain()}")
        try:
            measure_once(mock_produce, out_path=mock_out)
            print("2nd commit  → ERROR: guard did NOT fire!")
        except RuntimeError as e:
            print(f"2nd commit  → correctly REFUSED: {str(e)[:70]}...")
        r3 = measure_once(mock_produce, override=OVERRIDE_PHRASE, out_path=mock_out)
        print(f"override    → allowed 2nd touch (auditable), n_touches={len(_completed_touches())}")
        # tamper detection
        lines = tmp.read_text().splitlines()
        bad = json.loads(lines[0]); bad["score"] = 0.99
        tmp.write_text(json.dumps(bad) + "\n" + "\n".join(lines[1:]))
        print(f"tamper test → chain_ok after edit = {verify_ledger_chain()} (expect False)")
    elif args.dry_run:
        print(json.dumps(measure_once(lambda: ([], "", {}), dry_run=True), indent=2))
    elif args.commit:
        print("Real one-shot requires produce_fn wired to the RA harness (Phase 3, P3.2).")
        print("Refusing to run a bare --commit with no producer. Use P3.2 driver.")
    else:
        ap.print_help()
