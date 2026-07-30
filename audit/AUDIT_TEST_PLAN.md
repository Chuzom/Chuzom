# Chuzom Audit — Missing Test Plan

Deterministic, hermetic tests to add for each confirmed Critical/High (fail at `f5bf55c`, pass after fix). Do NOT weaken assertions to match current behavior.

## Critical
- **CHZ-AUD-D-01 (cache secret leak):** plant a known secret in a prompt+response; run through `result_cache`/`semantic_cache` store; assert (a) the on-disk `.db` bytes do NOT contain the secret (redaction applied), and (b) the DB file mode is `0600`. Also assert a TTL/retention bound exists.
- **CHZ-AUD-B-04 (SessionBuffer cross-project leak):** record content under project A, switch `CHUZOM_PROJECT_ID` to B in the same process, build B's context payload; assert A's content is absent. (Requires `get_session_buffer()` keyed by project/session.)

## High
- **CHZ-AUD-D-05 (false "never blocks"):** guard test that scans installed `rules/chuzom.md` + banner text for "no tool is ever blocked"/"never blocks" and fails while default enforce actually blocks Edit/Write — i.e. force the wording to match `resolve_enforce_mode()`'s real behavior.
- **CHZ-AUD-A-03 (advisory vs authoritative):** drive `auto-route.py` in default mode; assert `decision == "approve"` (advisory) and that a routing-guarantee doc/matrix marks push external-execution as NOT guaranteed unless zero-Claude.
- **CHZ-AUD-A-01 (failed attempts unlogged):** inject 2 failures + 1 success into the dispatch loop; assert the execution ledger contains `attempt_failed` rows for the 2 failures.
- **CHZ-AUD-A-04 (malformed stdin bypass):** feed `auto-route.py` malformed stdin JSON; assert it fails CLOSED to a safe pass-through with a logged error, not a silent total bypass (or that the behavior is explicitly the documented, intended skip).
- **CHZ-AUD-B-02 (unbounded plaintext retention):** assert durable session_store enforces a TTL/size bound and offers redaction when configured.
- **CHZ-AUD-B-05 (emergency fallback skips recording):** drive the emergency-BUDGET success path; assert session_spend + routing-quality ledger + SessionBuffer each got the turn.
- **CHZ-AUD-C-01 (session_store lost write):** N concurrent multi-process `record_event()` writers; assert count(persisted) == N (no silent loss).
- **CHZ-AUD-C-02 (circuit breaker overrides model_override):** set `model_override=X`, trip the breaker (3 low scores); assert the call still uses X.

## Medium (representative)
- CHZ-AUD-C-04: `chuzom verify` must check all 13 installed hooks. CHZ-AUD-C-05: IDE-config writers must not write into an unrelated cwd repo without an explicit target. Plus redaction/observability/classification mediums per `AUDIT_FINDINGS.json`.

## Environment gaps to close (UNABLE TO VERIFY this run)
- Python 3.10 / 3.12 / 3.13 (only 3.11 installed) — run the suite on each.
- Real-provider integration (Ollama/Codex/Gemini/OpenAI) and true multi-process/soak at 5000+ with provider restarts.
- Semantic-cache project-scoping (B marked UNABLE TO VERIFY).
