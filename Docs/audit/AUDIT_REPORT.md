# Chuzom — Independent Evidence-Based Audit

**Verdict: FAIL** (not safe to describe as production-ready or to make an "always routes / always executes another model" claim as-is).
Scope note: this is a *targeted* FAIL — the routing/budget/uninstall engine is reliable; the blockers are **privacy** (two confirmed secret-leak Criticals) and **claim accuracy** (a materially false "never blocks / always routes" claim). All blockers are fixable.

- **Commit audited:** `f5bf55c2a6e532229979ed90d376557f33698f57`
- **Checkout:** local `/Users/yaliandrona/Projects/Chuzom` (the audited artifact; GitHub was NOT used)
- **Environment:** macOS (darwin), Python **3.11.15** only (3.10/3.12/3.13 → UNABLE TO VERIFY — not installed)
- **Method:** four independent auditors, each EXECUTING real tests in hermetic tmp HOMEs with a fake-provider canary harness; nothing accepted on documentation/comment alone; the developer's real `~/.chuzom`/`~/.claude`/credentials were not used.
- **Full suite at audited commit:** 6485 passed / 0 failed / 0 error; `ruff` clean.

## Commands executed (representative)
```
git rev-parse HEAD            → f5bf55c…
.venv/bin/ruff check src/chuzom/   → All checks passed
.venv/bin/pytest -m "not slow and not requires_ollama and not requires_api_keys"  → 6485 passed
python -m build (via C, clean venv) → wheel builds/installs/imports/CLI/MCP/hook-install/uninstall all clean
+ ~40 canary routing drives, subprocess hook drives, concurrency (400 budget / 1200 session_store), soak N=5418
```

## Architecture / routing-path map (verified)
- **Push routing (Claude Code):** `UserPromptSubmit` hook `auto-route.py` intercepts every eligible prompt, classifies, and (default mode) calls a real external model, returning the result as **advisory context** (`decision:"approve"`). Claude still receives the raw prompt and may answer itself. Only `CHUZOM_ZERO_CLAUDE=1` converts a successful route into an authoritative turn replacement (`decision:"block"`).
- **Enforcement (`enforce-route.py`, PreToolUse):** default `CHUZOM_ENFORCE=smart` **holds/blocks** reasoning + code-edit tools (Edit/Write/MultiEdit/Bash) until a route is called — contradicting the "never blocks" messaging.
- **Pull routing (Cursor/Copilot/Windsurf/Gemini/OpenCode/etc.):** best-effort — the host model *decides* whether to call a Chuzom MCP tool. No hard interception.
- **MCP tools (`llm_*`):** route text→provider→text with canary-verified correct provider selection.
- **Budget/spend:** SQLite/WAL envelope + quota, verified concurrency-safe (400 concurrent, exact balances).
- **Persistence:** durable `session_store` (JSONL per project/session) holds verbatim content; `usage.db`/spend/quality ledgers hold metadata only.

## Findings — 26 total (2 Critical, 7 High, 1 Medium-High, 10 Medium, 4 Low, 2 Info)
Full detail + reproductions in `AUDIT_FINDINGS.json` and the per-track evidence files (`A/B/C/D-*.md`).

### Release blockers (Critical)
| ID | Title | Evidence |
|----|-------|----------|
| **CHZ-AUD-D-01** | Result-cache + semantic-cache persist **raw, unredacted** prompt/response (incl. planted `sk-ant-…`, AWS key, password) into **world-readable 0644** SQLite, indefinitely, full-text-indexed; the existing redactor never touches these write paths. | Planted secrets → raw byte-grep of the on-disk `.db` matched. |
| **CHZ-AUD-B-04** | In-process `SessionBuffer` is an **unscoped global singleton** (no project/session key). A long-lived process (MCP server) that serves >1 project leaks one project's verbatim prompts/responses (incl. secrets) into another project's outbound context payload. | Live repro: secret under `project-alpha` appeared in `project-beta`'s payload after `CHUZOM_PROJECT_ID` change mid-process. |

### High
| ID | Title |
|----|-------|
| CHZ-AUD-D-05 | Installed `rules/chuzom.md` + SessionStart banner claim "**no tool is ever blocked / advise mode**", but default `smart` **blocks** Edit/Write/MultiEdit (and blocked this auditor's Bash live). Claim FALSE; contradicts the repo's own `Docs/configuration.md`. |
| CHZ-AUD-A-03 | In default (non-zero-Claude) mode the push hook **never guarantees** the external result is authoritative — Claude may answer itself. Any "always executes another model" claim is unsupported for the default path. |
| CHZ-AUD-A-01 | Failed provider attempts are **never** written to the execution ledger (`attempt_failed` declared, never emitted) → savings/cost dashboards under-count real attempts. |
| CHZ-AUD-B-02 | Durable `session_store` persists **full verbatim plaintext** prompt/response content indefinitely (size-compaction only, no TTL, no redaction). |
| CHZ-AUD-B-05 | The emergency-BUDGET fallback success path **skips** session_spend, the routing-quality ledger, and SessionBuffer recording → invisible spend + missing context. |
| CHZ-AUD-C-01 | `session_store.record_event()` **loses writes** under real concurrent multi-process access (22/1200 = 1.83% silently vanished; tempfile+`os.replace` compaction race, no locking). |
| CHZ-AUD-C-02 | `model_override` is **silently overridden** by the process-global quality-feedback circuit breaker after 3 low-quality calls (99.94% of a 5418-call soak redirected); docstring "use only this model" is violated; unscoped `_quality_store` enables cross-caller poisoning. |

### Medium-High / Medium (selected)
- CHZ-AUD-A-04 (Med-High): **malformed/unparseable stdin JSON silently bypasses** `auto-route.py` entirely (fail-open) — a class of prompts escapes routing.
- CHZ-AUD-C-04: `chuzom verify` checks only 3 of the 13 hooks it installs. CHZ-AUD-C-05: 6 IDE-config writers use unguarded `Path.cwd()`. Plus redaction/observability/classification Mediums (see JSON).

## Assessments
- **Routing guarantee:** interception on the push path is reliable (100% canary coverage, 0% wrong-provider); **external execution as the answer is NOT guaranteed** in default mode (advisory only) — see `ROUTING_GUARANTEE_MATRIX.md`. Pull integrations are best-effort, not guaranteed.
- **Context persistence:** content persists in ONE durable store (verbatim, unbounded, plaintext); most stores are metadata-only. In-process buffer leaks cross-project (Critical). See `CONTEXT_PERSISTENCE_MATRIX.md`.
- **Reliability:** budget/spend concurrency PASS; soak (N=5418) shows no resource leak/token drift; BUT session_store has a real lost-write race and the circuit-breaker silently overrides model_override.
- **Security/privacy:** two Critical secret-leak paths (cache + in-process buffer); SQL-injection search closed negative; other injection/SSRF/path-traversal not found exploitable in this pass.
- **Packaging:** wheel builds, installs into a clean venv, imports, CLIs, MCP, hook-install/uninstall all clean; required modules present. Installed package matches source behavior.
- **Claims:** several FALSE/MISLEADING (see `CLAIMS_VERIFICATION.md`) — chiefly "never blocks", and conflating push (guaranteed interception) with pull (best-effort) and with "always executes another model".

## Recommended release blockers (must fix before a production / privacy-sensitive release or an "always routes" claim)
1. **CHZ-AUD-D-01** — redact + `0600` + TTL on cache writes (route them through `enterprise/redaction.py`).
2. **CHZ-AUD-B-04** — scope `SessionBuffer` by (project_id, session_id); never share one buffer across projects.
3. **CHZ-AUD-D-05 / A-03** — correct the "never blocks" and "always routes/executes" claims to match actual advise+enforce behavior; separate push (guaranteed interception) from pull (best-effort) and from execution (not authoritative unless zero-Claude).
4. **CHZ-AUD-C-01** — lock/atomic-append `session_store.record_event()`.
5. **CHZ-AUD-C-02** — make `model_override` bypass the circuit breaker (and scope `_quality_store`).
6. **CHZ-AUD-B-05 / A-01 / A-04** — record emergency-fallback + failed attempts; don't fail-open silently on malformed hook stdin.
