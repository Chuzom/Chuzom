"""chuzom audit — operate on the tamper-evident audit log.

Surfaces two primitives that already lived on :class:`AuditLog` but had no
operator-facing entry point:

* ``chuzom audit verify [--json]`` — walk the hash chain and prove integrity.
  Exit 0 when intact, exit 1 when tampering is detected (so it drops into a
  cron / CI gate). ``--json`` emits a machine-readable record for a SIEM.
* ``chuzom audit export [--format cef|json|csv] [--limit N]`` — dump the log in
  the format a SIEM ingests (CEF by default).

The audit DB path comes from ``CHUZOM_AUDIT_PATH`` (default ``~/.chuzom/audit.db``),
matching :class:`AuditLog`'s own resolution.

🥷 Backslash-Security: using vibe-coding rules for Logging & Error Handling
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    from chuzom.enterprise.audit import AuditLog, TamperDetected
except ImportError:  # enterprise/ is excluded from public distributions (gated by is_enterprise())
    AuditLog = TamperDetected = None  # type: ignore

_USAGE = (
    "chuzom audit — tamper-evident audit log operations\n"
    "\n"
    "Commands:\n"
    "  verify [--json]                 verify the hash chain (exit 1 on tamper)\n"
    "  export [--format FMT] [--limit N]\n"
    "                                  dump the log (FMT: cef|json|csv)\n"
)


def _verify(args: argparse.Namespace) -> int:
    log = AuditLog()
    rows = log.count()
    try:
        log.verify_chain()
    except TamperDetected as exc:
        if args.json:
            print(json.dumps({
                "verified": False, "rows_checked": rows,
                "tamper_row": exc.row_index, "detail": str(exc),
            }))
        else:
            print(f"❌ TAMPER DETECTED at row {exc.row_index}: {exc}", file=sys.stderr)
            print("   The audit log was modified outside the API. Investigate "
                  "and restore from a trusted backup.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"verified": True, "rows_checked": rows}))
    else:
        print(f"✅ Audit chain verified — {rows} events, hash chain intact.")
    return 0


def _export(args: argparse.Namespace) -> int:
    log = AuditLog()
    fmt = args.format
    if fmt == "cef":
        print(log.export_cef(limit=args.limit))
    elif fmt == "json":
        print(log.export_json(limit=args.limit))
    elif fmt == "csv":
        print(log.export_csv(limit=args.limit))
    else:  # pragma: no cover - argparse choices guard this
        print(f"unknown format: {fmt}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chuzom audit", description="Tamper-evident audit log operations",
        usage=_USAGE,
    )
    sub = parser.add_subparsers(dest="command")

    p_verify = sub.add_parser("verify", help="verify the hash chain")
    p_verify.add_argument("--json", action="store_true", help="machine-readable output")

    p_export = sub.add_parser("export", help="dump the log for a SIEM")
    p_export.add_argument(
        "--format", choices=("cef", "json", "csv"), default="cef",
        help="output format (default: cef)",
    )
    p_export.add_argument("--limit", type=int, default=1000, help="max rows (default: 1000)")

    args = parser.parse_args(argv)
    if args.command == "verify":
        return _verify(args)
    if args.command == "export":
        return _export(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
