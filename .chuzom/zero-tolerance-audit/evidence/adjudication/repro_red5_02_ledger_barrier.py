"""
RED5-02 attack vector (f), attempt 2: barrier-synchronized cold-start race.

The plain sequential-Popen version (repro_red5_02_ledger_multiproc.py) produced
ZERO False returns across 2400 calls (5 iterations x 24 procs x 20 writes),
unlike RED5-01's LineageStore reproducer which hit 4/12 crashes on its very
first run using the same sequential-Popen technique. Hypothesis: Popen spawn
+ Python interpreter startup latency naturally staggers each worker's first
_connect() call enough that true simultaneity at the DB-file-creation instant
is rare -- OR execution_ledger's 30s busy_timeout (raised from 5s per its own
code comment, specifically to fix this exact class of bug once already)
already absorbs the contention that LineageStore's constructor did not.

This version uses a filesystem barrier (a "go" file each worker busy-polls
for) to force all N worker processes to hit _connect()/record_event() at
virtually the same instant, immediately after process startup completes,
maximizing the chance of catching the true cold-start race window.

SAFETY: identical explicit path= mechanism as the prior script; same
print+assert gate in parent and every worker before any write.
"""
import sys
import os
import subprocess
import tempfile
import time
from pathlib import Path

WORKER_CODE = r'''
import sys, os, time
sys.path.insert(0, sys.argv[1])
tmpdir = sys.argv[2]
target_db = sys.argv[3]
go_file = sys.argv[4]
n_writes = int(sys.argv[5])

resolved = os.path.abspath(target_db)
assert resolved.startswith(os.path.abspath(tmpdir) + os.sep), (
    f"REFUSING: resolved path {resolved!r} is not under sandbox tmpdir {tmpdir!r}"
)

from pathlib import Path as _Path
from chuzom.execution_ledger import LedgerEvent, record_event

# Busy-poll for the barrier release -- maximizes simultaneity of the first
# _connect() call across all worker processes (the true cold-start instant).
while not os.path.exists(go_file):
    pass

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

def run_one(worktree_src, tmproot, n_procs, n_writes, iteration_tag):
    tmpdir = os.path.join(tmproot, f"iter-{iteration_tag}")
    os.makedirs(tmpdir)
    target_db = os.path.join(tmpdir, "usage.db")
    go_file = os.path.join(tmpdir, "GO")
    assert os.path.abspath(target_db).startswith(os.path.abspath(tmpdir) + os.sep)
    assert not os.path.exists(target_db)

    worker_script = os.path.join(tmpdir, "_worker.py")
    with open(worker_script, "w") as f:
        f.write(WORKER_CODE)

    procs = []
    for _ in range(n_procs):
        p = subprocess.Popen(
            [sys.executable, worker_script, worktree_src, tmpdir, target_db, go_file, str(n_writes)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        procs.append(p)

    # Give all interpreters time to reach the busy-poll loop, then release
    # them all at once.
    time.sleep(0.35)
    Path(go_file).touch()

    total_ok = total_false = total_exc = crashed = 0
    for p in procs:
        out, _ = p.communicate()
        if p.returncode != 0:
            crashed += 1
            print(f"  PROC_CRASHED rc={p.returncode}\n{out}")
        for line in out.splitlines():
            if line.startswith("WORKER_DONE"):
                parts = dict(kv.split("=") for kv in line.split()[1:])
                total_ok += int(parts["ok"])
                total_false += int(parts["false"])
                total_exc += int(parts["exc"])
            elif line.startswith("WORKER_EXCEPTION"):
                print(f"  {line}")

    import sqlite3
    row_count = "DB_NEVER_CREATED"
    if os.path.exists(target_db):
        conn = sqlite3.connect(target_db)
        try:
            row_count = conn.execute("SELECT COUNT(*) FROM execution_events").fetchone()[0]
        except sqlite3.OperationalError as e:
            row_count = f"QUERY_FAILED: {e}"
        conn.close()

    expected_total = n_procs * n_writes
    return dict(ok=total_ok, false=total_false, exc=total_exc, crashed=crashed,
                row_count=row_count, expected=expected_total)


def main():
    worktree_src = sys.argv[1]
    n_procs = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    n_writes = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    n_iters = int(sys.argv[4]) if len(sys.argv) > 4 else 10

    with tempfile.TemporaryDirectory(prefix="red5-02-barrier-") as tmproot:
        print(f"PARENT_SAFE_ROOT {tmproot}")
        grand_ok = grand_false = grand_exc = grand_crashed = 0
        for it in range(n_iters):
            r = run_one(worktree_src, tmproot, n_procs, n_writes, it)
            mismatch = "" if r["row_count"] == r["ok"] else "  <-- MISMATCH vs ok count!"
            print(f"iter={it:2d} ok={r['ok']:4d} false={r['false']:3d} exc={r['exc']:3d} "
                  f"crashed={r['crashed']:2d} db_rows={r['row_count']} expected={r['expected']}{mismatch}")
            grand_ok += r["ok"]; grand_false += r["false"]; grand_exc += r["exc"]; grand_crashed += r["crashed"]

        print(f"\n=== GRAND TOTAL over {n_iters} iterations x {n_procs} procs x {n_writes} writes "
              f"= {n_iters*n_procs*n_writes} calls ===")
        print(f"True={grand_ok} False={grand_false} Exceptions={grand_exc} ProcessCrashes={grand_crashed}")

if __name__ == "__main__":
    main()
