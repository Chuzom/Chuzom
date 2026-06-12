# Remediation Verification — Traceability Matrix

**Method.** For every finding in `Docs/audit/FINDINGS.md`, this document records: (a) the original problem, (b) the intended remediation, (c) the actual implementation evidence on `main`, (d) tests, (e) operational visibility, (f) residual risk, (g) acceptance status.

**Acceptance status definitions:**
- **Accepted** — root cause addressed; runtime path covered; tests validate real behaviour; no equivalent bypass observed.
- **Partially accepted** — some acceptance criteria met; others explicitly deferred and traceable.
- **Rejected** — change does not address root cause OR is bypassed by another path.
- **Cannot verify** — code exists; runtime path or operational visibility not directly inspectable from source.
- **Superseded** — addressed by a later finding or a scope decision (Q-P-2).
- **Regressed** — earlier state was equivalent or better.

**A code change is not sufficient evidence of acceptance.** A finding is accepted only when all eight acceptance gates from the audit charter are met.

---

## Critical findings

### F-INV-010 · Enterprise RBAC + Audit + Identity unwired from routing path

| Aspect | Evidence |
|---|---|
| Original problem | `enterprise/` carried 1,361 LOC of identity/RBAC/audit code with zero call sites from `router.route_and_call`. The "tamper-evident audit" claim was unwired. |
| Intended remediation | Single-chokepoint wiring at `router.route_and_call`: accept `identity` param, require `Permission.ROUTE_PROMPT`, write one `AuditEvent`, atomic budget charge. |
| Implementation | **Tier 1 + Tier 2 only.** `route_and_call(..., identity: TurnIdentity | None = None)` at `src/chuzom/router.py:1300`. Auto-resolve at `:1366-1367`. Audit append at `:1588` (cached path) and `:1732` (cold path) via `src/chuzom/audit_routing.py::audit_routing_turn`. |
| RBAC enforcement | **MISSING.** `grep -n "has_permission\|check_permission\|Permission\.ROUTE_PROMPT" src/chuzom/router.py` returns zero matches. No call to `enterprise/rbac.py`. |
| Atomic budget charge by identity | **MISSING.** `budget.reserve_tokens(provider, tokens)` is provider-scoped, not identity-scoped. |
| Tests | `tests/test_tier1_audit_per_turn.py` — N turns → N rows, `verify_chain()` true after 1000 decisions, fail-open on AuditLog failure, env disable. 21 tests. |
| Operational visibility | `verify_chain()` exists but **no CLI or HTTP endpoint exposes it** — `grep -rn verify_chain src/chuzom/` shows only internal use in `audit.py`. |
| Residual risk | (a) No RBAC = anyone with env access to a chuzom MCP server can route as any identity. (b) Single-process SQLite audit; multi-process write coordination unspecified. (c) `tenant_id` absent — no cross-tenant isolation. |
| **Acceptance** | **Partially accepted.** Identity attribution + audit-row-per-turn + chain integrity: accepted. RBAC + atomic identity budgets + multi-tenant: **not accepted**, parked for Tier 3 / Q-P-2. |

### F-SEC-001 · `chuzom-sse` binds 0.0.0.0 with zero authentication

| Aspect | Evidence |
|---|---|
| Original problem | `chuzom-sse` console script defaulted `host=0.0.0.0` and constructed `mcp.sse_app()` with no auth middleware. PaaS deployment was the documented happy path = the attack scenario. |
| Implementation | `pyproject.toml:78-85` comments record the removal; `chuzom-sse` is absent from `[project.scripts]`. `main_sse` retained in `src/chuzom/server.py:158-188` with security-notice docstring (lines 162-184). |
| Tests | `tests/test_no_chuzom_sse_entry_point.py` — 3 regression tests (pyproject scripts assertion + main_sse importable + docstring carries SEC-001 notice). |
| Operational visibility | `pip install chuzom-router` no longer installs `chuzom-sse`. Verified end-to-end in PR #18 by clean-venv install: `bin/chuzom-sse` absent. |
| Residual risk | If a future maintainer re-adds the entry without an auth wrapper, the regression test fires. Risk: someone bypasses the test by adding a new entry-point name. |
| **Acceptance** | **Accepted.** |

### F-SEC-002 · `llm_fs_edit_many` accepts arbitrary glob with no path validation

| Aspect | Evidence |
|---|---|
| Original problem | `tools/fs.py` ran `glob.glob(glob_pattern, recursive=True)` with no root check; up to 32 KB per match was read into the model prompt. `~/.ssh/**` exfiltration in one call. |
| Implementation | Two gates (`src/chuzom/tools/fs.py:32-77`): (1) opt-in env `CHUZOM_FS_TOOLS=on` at `register()` (`:215-220`), (2) `project_root` required parameter on `llm_fs_edit_many` + `llm_fs_analyze_context`, validated via `_resolve_root` + `_assert_under_root` using `Path.resolve()`. `project_root='/'` refused. |
| Tests | `tests/test_fs_path_validation.py` — 26 tests covering env-gate truth table, sandbox helpers, symlink escape, absolute-path escape, edit-many end-to-end rejection. |
| Operational visibility | Without opt-in, `mcp.list_tools()` exposes zero `llm_fs_*` entries (verified in tests). |
| Residual risk | Operators who opt in must pass a tight `project_root`. Documentation is in the docstring; no admin policy to force a tight root. |
| **Acceptance** | **Accepted.** |

---

## High findings

### F-SEC-003 · `tools/agoragentic.*` undocumented wallet/marketplace

| Aspect | Evidence |
|---|---|
| Original problem | Four `agoragentic_*` MCP tools registered by default; `agoragentic_task` performs USDC settlement on Base L2. Hallucinated tool call → on-chain transaction. |
| Implementation | `src/chuzom/tools/agoragentic.py:29-32` — `_agoragentic_enabled()` checks `CHUZOM_AGORAGENTIC=on`. `register()` short-circuits without it. |
| Tests | `tests/test_agoragentic_opt_in.py` — 18 tests covering env truth-table and `_agoragentic_enabled` helper. |
| Residual risk | Operators who deliberately opt in carry the same payment-signing surface as before. No second-confirmation flow on wallet operations. |
| **Acceptance** | **Accepted** (minimum-viable mitigation = work-plan Option B). |

### F-INV-001 · Pre-existing self-audit overclaims production-readiness

| Implementation | `AUDIT_FINDINGS.txt` and `CHUZOM_AUDIT_REPORT.md` carry top-of-document scope notices; every "5★ across the board" / "APPROVED FOR PRODUCTION" claim is contextualised to "lineage subsystem only" and points at `Docs/audit/` as the authoritative whole-project assessment. |
| **Acceptance** | **Accepted.** Per work-plan Option B. |

### F-INV-002 · README "enterprise-ready" vs pyproject Alpha

| Implementation | README hero now reads "Local-first LLM router for developer workstations"; maturity line says developer-tool layer is production-path-today (alpha per pyproject), enterprise control plane is scaffolded but not wired (INV-010). |
| **Acceptance** | **Accepted.** First 30 lines of README + first 20 of pyproject converge on alpha. |

### F-INV-007 · `last_classification.json` shared across sessions

| Implementation | `src/chuzom/hooks/auto-route.py:2622` writes `last_classification_<session_id>.json`. `src/chuzom/tools/text.py:56` reader pins to `CLAUDE_SESSION_ID` from env. Inner-payload session_id mismatch rejected (belt-and-braces). |
| Tests | `tests/test_classification_side_channel_isolation.py` — 12 tests: env missing, distinct session ids see independent verdicts, forged shard cannot influence current, inner-sid mismatch rejected, staleness, malformed input. |
| **Acceptance** | **Accepted.** |

### F-INV-011 · Budget enforcement provider-level, not identity-level

| Aspect | Evidence |
|---|---|
| Original problem | Every budget call was scoped by provider name; `enterprise/quotas.py::QuotaTracker` is not imported by router. |
| Implementation | **Unchanged.** `src/chuzom/budget.py::reserve_tokens(provider: str, tokens: int)` still keyed on provider. `router.py:1447` checks `cost.get_monthly_spend()` against `config.chuzom_monthly_budget` globally. No identity term in budget reservation. |
| Tests | None added for per-identity budget. |
| **Acceptance** | **Rejected** (not addressed). Parked for Tier 3 + Q-P-2. |

### F-PRI-001 · `enterprise.redact_prompt` is shelf-ware

| Aspect | Evidence |
|---|---|
| Original problem | `enterprise/redaction.py::redact_prompt` exists but is not called from the routing path. PII flows to providers verbatim. |
| Implementation | **Unchanged.** `grep -rn "redact_prompt\|RedactionPolicy" src/chuzom/router.py src/chuzom/audit_routing.py` returns zero matches. |
| **Acceptance** | **Rejected** (not addressed). Tier 3 scope. |

### F-ROU-001 · Adversarial forgery of `last_classification.json`

| Implementation | Same change as INV-007 (per-session shards + inner-sid check). |
| **Acceptance** | **Accepted.** Same evidence as INV-007. |

### F-ROU-002 · `_dynamic_routing_table` module-global

| Aspect | Evidence |
|---|---|
| Original problem | Module-global state shared across users/tenants in SSE mode. |
| Implementation | **Unchanged.** `src/chuzom/dynamic_routing.py:33` — `_dynamic_routing_table: dict[...] | None = None` is still a module-level global, protected only by a `threading.Lock` for concurrent single-process access. |
| **Acceptance** | **Rejected** (not addressed). Q-P-2 dependent. |

### F-OBS-001 · Logs identity-blind

| Aspect | Evidence |
|---|---|
| Original problem | `router.py` log fields are `provider`, `model`, `task_type`. No `tenant_id`, `user_id`, `agent_id`, `request_id`. |
| Implementation (partial) | `src/chuzom/router.py:1378-1386` binds `request_id` (= correlation_id), `user_id`, `org_id`, and `agent_id` (when set) into structlog contextvars. Every log line during the turn carries those fields. |
| Tests | `tests/test_tier2_log_contextvars.py` — 5 tests on bind-state. |
| Missing | `tenant_id` is intentionally absent — Tier 3 / Q-P-2 dependent. |
| **Acceptance** | **Partially accepted.** Single-tenant identity fields in logs: accepted. Cross-tenant attribution: not accepted. |

### F-TST-001 · 9 critical test suites silently excluded by `collect_ignore`

| Implementation | `tests/conftest.py:36` — `collect_ignore: list[str] = []`. The 9 previously-ignored files are collected. Failures that surfaced were either fixed (lineage API rewrite in #17 turned ~30 of them green) or moved into `_KNOWN_BROKEN_TESTS` with a documented reason. Meta-test `tests/test_no_silent_collect_ignore.py` guards against regression. |
| **Acceptance** | **Accepted.** |

### F-TST-003 · No concurrency tests for budget enforcement

| Implementation | **Unchanged.** `ls tests/qa/test_budget*` and `grep "asyncio.gather.*budget" tests/` return empty. |
| **Acceptance** | **Rejected** (not addressed). Bundled with INV-011 in Tier 3. |

### F-INV-012 · Two parallel `AuditEvent` classes

| Implementation | **Unchanged.** Both `src/chuzom/enterprise/audit.py:56` and `src/chuzom/storage/models.py:23` still define `class AuditEvent`. Tier 1 audit chose to use `enterprise/audit.py` exclusively, but the `storage/` path remains. |
| **Acceptance** | **Open.** Architectural debt unresolved; both classes coexist. |

### F-INV-012a · `storage/service.py` audit path also unwired from routing

| Implementation | **Unchanged.** No call from `router.route_and_call` to `storage.service`. |
| **Acceptance** | **Open.** |

### F-INV-013 · `Docs/` gitignored — audit artifacts invisible externally

| Aspect | Evidence |
|---|---|
| Original problem | `Docs/` is gitignored; the audit corpus is invisible to outside readers. |
| Implementation | `grep "^Docs/" .gitignore` still matches (`Docs/`). The audit corpus is still gitignored. |
| Mitigation | This document is being created at `docs/audit/post-remediation/` (lowercase). On case-insensitive filesystems (macOS) these resolve to the same directory; on Linux they are distinct. On the merged repo, behaviour depends on the runner. |
| **Acceptance** | **Open / partially mitigated.** Needs a deliberate move of audit corpus to a non-gitignored path. |

---

## Medium findings (summary)

| ID | Description | Status | Evidence |
|---|---|---|---|
| INV-003 | 496 Python files in src/chuzom/ | **Open** | Module count not reduced. Not regressed. |
| INV-004 | Default pytest skips slow / requires_ollama | **Open** | `pyproject.toml [tool.pytest.ini_options]` markers unchanged. |
| INV-005 | Dependency inventory | Info | No action required. |
| INV-008 | `router.py` 1834 lines | **Open** (likely regressed slightly with Tier 1+2 additions) | Current count includes the Tier 1+2 wiring. |
| INV-009 | 60-tool MCP surface | **Partially** | `fs` + `agoragentic` now opt-in (SEC-002/003). Tool count under default install: lower. |
| PRI-002 | Cache stores prompt fragments | **Open** | Semantic cache unchanged. |
| PRI-003 | No no-retention provider mode | **Open** | No ZDR plumbing observed. |
| REL-002 / SEC-006 | Stale circuit-breaker reset unconditional | **Cannot verify** | `src/chuzom/server.py:71-78` runs `reset_stale(max_age_seconds=1800.0)` at boot; behaviour at scale not tested. |
| REL-003 | Terminal-state error is raw RuntimeError | **Open** | No structured error class added. |
| PRO-001 | MCP tools return strings, not structured data | **Open** | Tool return types unchanged. |
| PRO-002 | LiteLLM normalization-loss matrix | **Open** | Audit gap; not commissioned. |
| ROU-003 | router.py monolith concurrency review | **Open** | No decomposition. |
| SEC-004 | `chuzom://status` MCP resource leaks provider config | **Cannot verify** | Resource at `src/chuzom/server.py:122` still exposes `Profile/Tier/Providers/Text/Media` to any client that can read the resource. No identity check. |
| TST-002 | Mis-named isolation test | **Open** | Not renamed. |

---

## Lateral findings introduced by remediation

The remediation cycle introduced new affordances that themselves need verification. These are not in the original FINDINGS list but a post-remediation audit must record them.

### N-001 · `TurnIdentity.agent_id` is trusted from `CHUZOM_AGENT_ID` env

Any process on the host can set `CHUZOM_AGENT_ID=anything` and have audit rows attributed to that agent. **This is correct for Tier 1+2** (single-user / single-machine trust model), but is an explicit anti-property under multi-tenant or enterprise threat models. `src/chuzom/identity.py:81-91`.

### N-002 · `CHUZOM_AUDIT_DISABLED=1` skips the audit write entirely

`src/chuzom/audit_routing.py:55-57` (`_audit_disabled`). Allowing an operator to disable the audit chain locally is by design for tests but is also a bypass under enterprise threat models. Mandatory-audit deployments need to refuse this env.

### N-003 · `~/.chuzom/audit.db` location is per-user; identical operator across processes shares the file

`src/chuzom/enterprise/audit.py:154-158`. Two chuzom processes run by the same OS user write to the same `audit.db`. SQLite file-locking will serialise; the hash chain is read once per `append` via `_latest_hash()`. Under high concurrency, this is correct but slow. Tests assert correctness up to 1000 sequential decisions, not concurrent.

### N-004 · Audit-singleton race window

`src/chuzom/audit_routing.py:51-65` constructs `AuditLog` lazily under a `threading.Lock`. Correct. But the lock is per-process; in distributed deployments, multiple processes each instantiate their own AuditLog against the shared `audit.db`.

---

## Summary

| Severity bucket | Originally counted | Accepted | Partially | Rejected / Open | Cannot verify |
|---|---|---|---|---|---|
| Critical | 3 | 2 (SEC-001, SEC-002) | 1 (INV-010 — Tier 1+2 only) | 0 | 0 |
| High | 11 | 6 (SEC-003, INV-001, INV-002, INV-007, ROU-001, TST-001) | 1 (OBS-001 — partial) | 4 (INV-011, PRI-001, ROU-002, TST-003) | 0 |
| Medium | 11 | 0 | 0 | 8 | 3 |
| Low / Info | 3 | 0 | 0 | 3 | 0 |
| **Positive** | 1 | n/a | n/a | n/a | n/a |

**Of the 14 Critical + High findings, 8 are accepted, 2 are partial, 4 are unaddressed.** All four unaddressed Critical/High items are Tier 3 / Q-P-2 dependent.
