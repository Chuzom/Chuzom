#!/usr/bin/env python3
"""RED5 repro 01b: isolate whether concurrent APPEND (post cold-start) is safe.

Pre-creates the lineage store/db in the MAIN process first (single-threaded,
no race), THEN spawns N concurrent processes that ONLY call append() against
the already-initialized WAL db. This isolates the append-time busy_timeout/WAL
fix (commit 14bf8b1's actual subject) from the cold-start constructor race
found in repro_01 (multiple processes racing _init_db()/PRAGMA journal_mode=WAL
on a brand new file).
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
import sys
sys.path.insert(0, sys.argv[1])
from chuzom.lineage.lineage_store import LineageStore
from chuzom.lineage.decision_logger import RoutingDecision

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
    if len(sys.argv) < 2:
        print("usage: repro_01b_lineage_warm_append.py <worktree_src_path>")
        sys.exit(2)
    src_path = sys.argv[1]

    with tempfile.TemporaryDirectory(prefix="red5_lineage_warm_") as tmp:
        sandbox_home = Path(tmp) / "home"
        sandbox_home.mkdir()
        router_dir = str(sandbox_home / ".chuzom")

        # Pre-create in THIS process (no concurrency) so WAL mode is already
        # established on disk before any worker process touches the file.
        sys.path.insert(0, src_path)
        from chuzom.lineage.lineage_store import LineageStore
        LineageStore(router_dir=router_dir)  # cold-start happens here, alone

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

        locked_errors = 0
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            print(f"rc={proc.returncode} out={out.strip()!r}")
            if err.strip():
                print(f"  STDERR: {err.strip()[:1000]}")
                if "locked" in err.lower():
                    locked_errors += 1

        expected_total = N_PROCS * N_WRITES_PER_PROC
        jsonl_file = sandbox_home / ".chuzom" / "routing_lineage.jsonl"
        db_file = sandbox_home / ".chuzom" / "routing_lineage.db"

        raw_lines = jsonl_file.read_text(encoding="utf-8").splitlines()
        print(f"\njsonl raw line count: {len(raw_lines)} (expected {expected_total})")

        import sqlite3
        conn = sqlite3.connect(str(db_file))
        count = conn.execute("SELECT COUNT(*) FROM routing_decisions").fetchone()[0]
        conn.close()
        print(f"sqlite row count: {count} (expected {expected_total})")
        print(f"'database is locked' errors: {locked_errors}")


if __name__ == "__main__":
    main()
