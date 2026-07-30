# Iteration 9 — GATE results

`pytest -m "not slow and not requires_ollama and not requires_api_keys"`

| Stage | Result |
|-------|--------|
| Before iter-9 (fe175a0) | 6469 passed / 0 failed |
| After 8 fixes + manifest + new tests | **6475 passed / 0 failed / 0 error** (418s) |

- RED1-9-02 Critical (TOML over-match I introduced): fixed regex + backup; verified over-match cases preserve adjacent tables.
- Manifest verified end-to-end: real gemini install recorded 8 artifacts; uninstall replay removed all + cleared manifest.
- Banner is_fallback, install-backup, opencode/codex hooks all covered.

Verdict: FIX round complete, GATE-green. Clean-audit counter = 0.
