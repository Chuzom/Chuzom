#!/usr/bin/env python3
"""RED5 repro 01: lineage_store.py under REAL multi-process concurrent writers.

Spawns N separate OS processes (subprocess.Popen, not threads) that each call
LineageStore.append() many times, targeting the SAME jsonl+sqlite files under a
sandboxed HOME. Verifies:
  (a) no "database is locked" errors (checks the WAL/busy_timeout fix generalizes
      under real multi-process load, not just the codebase's own thread benchmark)
  (b) row count in sqlite == expected total
  (c) row count parseable from jsonl == expected total (proves/disproves interleaved
      torn writes from the complete absence of file locking on the jsonl sidecar)
  (d) whether query_jsonl() raises on the resulting file (proves/disproves the
      zero-tolerance-for-malformed-lines finding)

Must be run with the audit worktree's .venv-audit python only.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

N_PROCS = 12
N_WRITES_PER_PROC = 200

WORKER_CODE = r"""
import sys, os
sys.path.insert(0, sys.argv[1])
from chuzom.lineage.lineage_store import LineageStore
from chuzom.lineage.decision_logger import RoutingDecision
import time

router_dir = sys.argv[2]
proc_id = sys.argv[3]
n = int(sys.argv[4])

store = LineageStore(router_dir=router_dir)
errors = 0
for i in range(n):
    try:
        d = RoutingDecision(
            decision_id=f"proc{proc_id}-{i}",
            operation="repro",
            classification="query/simple",
            selected_model="test-model",
            selection_reason="repro",
            cost_usd=0.0001,
            latency_ms=1.0,
        )
        store.append(d)
    except Exception as e:
        errors += 1
        sys.stderr.write(f"WRITE_ERROR proc={proc_id} i={i} err={e!r}\n")
print(f"proc={proc_id} done errors={errors}")
"""


def main():
    worktree_src = Path(__file__).resolve()
    # locate worktree src dir by walking up from this script? Instead take as argv.
    if len(sys.argv) < 2:
        print("usage: repro_01_lineage_multiproc.py <worktree_src_path>")
        sys.exit(2)
    src_path = sys.argv[1]

    with tempfile.TemporaryDirectory(prefix="red5_lineage_") as tmp:
        sandbox_home = Path(tmp) / "home"
        sandbox_home.mkdir()
        router_dir = str(sandbox_home / ".chuzom")

        worker_script = Path(tmp) / "worker.py"
        worker_script.write_text(WORKER_CODE)

        env = dict(os.environ)
        env["HOME"] = str(sandbox_home)

        procs = []
        for p in range(N_PROCS):
            proc = subprocess.Popen(
                [sys.executable, str(worker_script), src_path, router_dir, str(p), str(N_WRITES_PER_PROC)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            procs.append(proc)

        results = []
        total_stderr = []
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            results.append((proc.returncode, out.strip(), err.strip()))
            if err.strip():
                total_stderr.append(err.strip())

        expected_total = N_PROCS * N_WRITES_PER_PROC

        print("=== Process results ===")
        locked_errors = 0
        for rc, out, err in results:
            print(f"rc={rc} out={out!r}")
            if err:
                print(f"  STDERR: {err[:2000]}")
                if "locked" in err.lower():
                    locked_errors += 1

        # Inspect resulting files
        jsonl_file = sandbox_home / ".chuzom" / "routing_lineage.jsonl"
        db_file = sandbox_home / ".chuzom" / "routing_lineage.db"
        print(f"\njsonl exists: {jsonl_file.exists()} path={jsonl_file}")
        print(f"db exists: {db_file.exists()} path={db_file}")

        # (c) raw line count + parse tolerance test
        if jsonl_file.exists():
            raw_lines = jsonl_file.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
            print(f"jsonl raw line count: {len(raw_lines)} (expected {expected_total})")
            parse_fail_idx = None
            parsed_ok = 0
            for idx, line in enumerate(raw_lines):
                try:
                    json.loads(line)
                    parsed_ok += 1
                except json.JSONDecodeError as e:
                    if parse_fail_idx is None:
                        parse_fail_idx = idx
                    print(f"  MALFORMED LINE at idx={idx}: {e} :: repr={line[:200]!r}")
            print(f"jsonl lines that parse individually: {parsed_ok}/{len(raw_lines)}")

            # (d) exercise the actual query_jsonl() reader to see if it raises
            try:
                sys.path.insert(0, src_path)
                from chuzom.lineage.lineage_store import LineageStore as LS2
                store2 = LS2(router_dir=router_dir)
                recs = store2.query_jsonl(limit=100000)
                print(f"query_jsonl() succeeded: returned {len(recs)} records")
            except Exception as e:
                print(f"query_jsonl() RAISED: {type(e).__name__}: {e}")

        # (b) sqlite row count
        if db_file.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            try:
                cur = conn.execute("SELECT COUNT(*) FROM routing_decisions")
                count = cur.fetchone()[0]
                print(f"sqlite routing_decisions row count: {count} (expected {expected_total})")
            finally:
                conn.close()

        print(f"\n'database is locked' errors observed: {locked_errors}")
        print(f"Total per-write exceptions across all procs: {sum(1 for _,_,e in results if 'WRITE_ERROR' in e)}")


if __name__ == "__main__":
    main()
