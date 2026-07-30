"""RED2-8-01/RED2-9-*: install/uninstall artifact manifest.

The multi-host installer writes to a large, growing set of surfaces (Claude Code,
Claude Desktop, claw-code, codex, cursor, gemini-cli, vscode, copilot-cli,
opencode, openclaw, trae, …). Uninstall was assembled per-host and repeatedly
missed subsets — every audit round found another gap. The structural fix is a
**manifest**: every write records what it did here; uninstall replays the records
in reverse. New surfaces are covered automatically as long as their write goes
through a recording helper, so the coverage can no longer silently drift.

Record kinds:
- ``json_mcp``     {path, root_key, server}  → remove root_key[server] from a JSON file
- ``toml_table``   {path, header}            → remove a ``[header]`` TOML table
- ``text_block``   {path, block}             → remove an exact appended text block
- ``created_file`` {path}                    → delete a whole file chuzom created
- ``file``         {path}                     → delete a copied file (e.g. a hook script)
- ``dir``          {path}                     → recursively delete a chuzom-created dir

All operations are best-effort and defensive: a manifest write must never break
install, and a single removal failure must never abort uninstall.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any


def _manifest_path() -> pathlib.Path:
    return pathlib.Path.home() / ".chuzom" / "install-manifest.json"


def _load() -> list[dict[str, Any]]:
    p = _manifest_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def record(kind: str, path: Any, **meta: Any) -> None:
    """Append an artifact record. Never raises — a manifest hiccup must not break
    install. De-duplicates identical records so repeated installs don't bloat it."""
    try:
        entry = {"kind": kind, "path": str(path), **meta}
        records = _load()
        if entry in records:
            return
        records.append(entry)
        p = _manifest_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(records, indent=2))
    except Exception:
        pass  # best-effort; install must proceed regardless


def clear() -> None:
    """Delete the manifest (after a successful uninstall replay)."""
    try:
        _manifest_path().unlink(missing_ok=True)
    except OSError:
        pass


def apply_uninstall() -> list[str]:
    """Replay the manifest in reverse, removing every recorded artifact.

    Returns human-readable action strings. Records are processed newest-first and
    each removal is independently guarded, so one failure never aborts the rest.
    On completion the manifest is cleared.
    """
    import shutil as _shutil

    actions: list[str] = []
    records = _load()
    for rec in reversed(records):
        try:
            kind = rec.get("kind")
            path = pathlib.Path(rec["path"])
            if kind == "json_mcp":
                actions += _remove_json_key(path, rec.get("root_key", "mcpServers"), rec.get("server", "chuzom"))
            elif kind == "toml_table":
                actions += _remove_toml_table(path, rec.get("header", ""))
            elif kind == "text_block":
                actions += _remove_text_block(path, rec.get("block", ""))
            elif kind in ("created_file", "file"):
                if path.exists():
                    path.unlink()
                    actions.append(f"✓ Removed {path}")
            elif kind == "dir":
                if path.exists():
                    _shutil.rmtree(path, ignore_errors=True)
                    actions.append(f"✓ Removed {path}")
        except Exception as e:  # noqa: BLE001 — one bad record must not abort the rest
            actions.append(f"  manifest removal skipped ({rec.get('path')}): {e}")
    clear()
    return actions


def _remove_json_key(path: pathlib.Path, root_key: str, server: str) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    servers = data.get(root_key)
    if isinstance(servers, dict) and server in servers:
        del servers[server]
        path.write_text(json.dumps(data, indent=2))
        return [f"✓ Removed {server} from {path}"]
    return []


def _remove_toml_table(path: pathlib.Path, header: str) -> list[str]:
    import re
    if not path.exists() or not header:
        return []
    text = path.read_text()
    # RED1-9-02: body stops at the next '[table]' line (^-anchored, MULTILINE) so
    # adjacent tables not separated by a blank line are NOT swallowed.
    pattern = re.compile(
        rf'(?m)^\[{re.escape(header)}\][^\n]*\n(?:(?!\[).*(?:\n|$))*'
    )
    updated = pattern.sub("", text, count=1)
    if updated != text:
        # Defensive backup before modifying a user's TOML config.
        try:
            _shutil = __import__("shutil")
            _shutil.copy2(path, path.with_suffix(path.suffix + ".chuzom-bak"))
        except OSError:
            pass
        path.write_text(updated)
        return [f"✓ Removed [{header}] from {path}"]
    return []


def _remove_text_block(path: pathlib.Path, block: str) -> list[str]:
    if not path.exists() or not block:
        return []
    text = path.read_text()
    if block in text:
        updated = text.replace(block, "", 1)
        # If the file is now empty/whitespace-only, remove it entirely.
        if updated.strip():
            path.write_text(updated)
        else:
            path.unlink()
        return [f"✓ Removed chuzom block from {path}"]
    return []
