# Iteration 6 — GATE results

`pytest -m "not slow and not requires_ollama and not requires_api_keys"`

| Stage | Result |
|-------|--------|
| Before iter-6 (1dd7401) | 6428 passed / 0 failed |
| After 5 fixes + new tests | 1 failed / 6448 passed |
| The 1 failure | `test_context.py::test_with_caller_context` — PRE-EXISTING non-hermetic test (missing the `reset_session_buffer` HOME-isolation fixture its siblings use); it read the real live `~/.chuzom` session accumulator, which this long session's context-capture hook had filled with the auditors' Bash commands. Proven independent of iter-6 code: it passes at 1dd7401 and fails on the current tree only due to real-store timing; I don't touch context.py/session_store. Fixed by adding the fixture. |
| After test-hermeticity fix | **clean** (see final line below) |

## Findings fixed this iteration
- RED2-6-01 (Critical): content-aware hook auto-update + stamp bumps (17→18, 26→27).
- RED2-6-03 (Medium): content-aware rules auto-update.
- RED2-6-02 (High): uninstall CLI now calls uninstall_claw_code + uninstall_ide_configs.
- RED1-6-01 (High): transitive parent-chain walk in all 3 budget backends.
- RED1-6-02 (High): render-mode allow-list, unrecognized values fail safe to echo.
- (test hygiene) test_with_caller_context made hermetic.

Verdict: FIX round complete. Clean-audit counter = 0 (code changed). Convergence needs the next fresh RED round clean, then a second clean round with no code change between.
