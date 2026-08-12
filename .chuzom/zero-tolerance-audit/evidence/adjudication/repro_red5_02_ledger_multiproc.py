"""
Safety-gated live multi-process reproducer for RED5-02.

SAFETY: uses execution_ledger.record_event(ev, path=<explicit tmpdir path>) --
the explicit `path=` keyword argument that _connect()/_db_path() honor BEFORE
ever falling back to the real ~/.chuzom/usage.db. This is the same
"explicit constructor/param override, never an env var" pattern the RED-5
safety appendix confirmed is provably safe for LineageStore/StorageService.
We print + assert the resolved path is inside our own tmpdir before any
write happens, in both the parent and every worker subprocess.

Usage (parent):
    <worktree>/.venv-audit/bin/python repro_red5_02_ledger_multiproc.py <worktree_src_dir>

Each worker subprocess:
  - imports chuzom.execution_ledger with sys.path pointed at <worktree>/src
  - resolves TARGET_DB from argv, asserts it is under the tmpdir passed on argv
  - calls record_event(LedgerEvent(...), path=TARGET_DB) N times in a tight loop,
    racing to be among the very first writers against a not-yet-existing DB file
  - prints one line per call: "RESULT <ok:0|1> <bool_return>"
  - never touches HOME, CHUZOM_HOME, or any other env var
"""
import sys
import os
import subprocess
import tempfile
import time
from pathlib import Path

WORKER_CODE = r'''
import sys, os
sys.path.insert(0, sys.argv[1])
tmpdir = sys.argv[2]
target_db = sys.argv[3]
n_writes = int(sys.argv[4])

# SAFETY GATE: prove the resolved path is inside our own tmpdir before any write.
resolved = os.path.abspath(target_db)
assert resolved.startswith(os.path.abspath(tmpdir) + os.sep), (
    f"REFUSING: resolved path {resolved!r} is not under sandbox tmpdir {tmpdir!r}"
)
print(f"WORKER_SAFE_PATH {resolved}", flush=True)

from pathlib import Path as _Path
from chuzom.execution_ledger import LedgerEvent, record_event

ok_count = 0
false_count = 0
exc_count = 0
for i in range(n_writes):
    ev = LedgerEvent(
        event_id=f"{os.getpid()}-{i}",
        session_id=f"sess-{os.getpid()}",
        route_id=f"route-{os.getpid()}-{i}",
        event_type="route_completed",
        task_type="query",
    )
    try:
        result = record_event(ev, path=_Path(target_db))
        if result:
            ok_count += 1
        else:
            false_count += 1
    except Exception as e:
        exc_count += 1
        print(f"WORKER_EXCEPTION {type(e).__name__}: {e}", flush=True)

print(f"WORKER_DONE pid={os.getpid()} ok={ok_count} false={false_count} exc={exc_count}", flush=True)
'''

def main():
    worktree_src = sys.argv[1]
    n_procs = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    n_writes = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    with tempfile.TemporaryDirectory(prefix="red5-02-adjudication-") as tmpdir:
        target_db = os.path.join(tmpdir, "usage.db")
        print(f"PARENT_SAFE_PATH {target_db}")
        assert os.path.abspath(target_db).startswith(os.path.abspath(tmpdir) + os.sep)
        assert not os.path.exists(target_db), "target DB must not pre-exist (cold-start test)"

        worker_script = os.path.join(tmpdir, "_worker.py")
        with open(worker_script, "w") as f:
            f.write(WORKER_CODE)

        procs = []
        t0 = time.time()
        for _ in range(n_procs):
            p = subprocess.Popen(
                [sys.executable, worker_script, worktree_src, tmpdir, target_db, str(n_writes)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            procs.append(p)

        total_ok = 0
        total_false = 0
        total_exc = 0
        crashed = 0
        for p in procs:
            out, _ = p.communicate()
            rc = p.returncode
            if rc != 0:
                crashed += 1
                print(f"PROC_CRASHED rc={rc}\n{out}")
            for line in out.splitlines():
                if line.startswith("WORKER_DONE"):
                    parts = dict(kv.split("=") for kv in line.split()[1:])
                    total_ok += int(parts["ok"])
                    total_false += int(parts["false"])
                    total_exc += int(parts["exc"])
                elif line.startswith("WORKER_EXCEPTION"):
                    print(line)
                elif line.startswith("WORKER_SAFE_PATH"):
                    pass  # already validated by worker's own assert

        elapsed = time.time() - t0
        expected_total = n_procs * n_writes

        # Now independently count actual rows in the DB (if it exists at all).
        import sqlite3
        row_count = None
        if os.path.exists(target_db):
            conn = sqlite3.connect(target_db)
            try:
                row_count = conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0]
            except sqlite3.OperationalError as e:
                row_count = f"QUERY_FAILED: {e}"
            conn.close()
        else:
            row_count = "DB_NEVER_CREATED"

        print(f"=== SUMMARY (elapsed={elapsed:.2f}s, {n_procs} procs x {n_writes} writes) ===")
        print(f"expected_total_calls={expected_total}")
        print(f"record_event()->True   total={total_ok}")
        print(f"record_event()->False  total={total_false}")
        print(f"record_event()raised   total={total_exc}  (should be 0 -- record_event never raises)")
        print(f"processes_crashed(rc!=0)={crashed}  (should be 0 -- record_event never raises, unlike LineageStore)")
        print(f"actual_db_row_count={row_count}")
        print(f"accounted_for = ok+false+exc = {total_ok + total_false + total_exc} (should equal expected_total={expected_total})")

if __name__ == "__main__":
    main()
