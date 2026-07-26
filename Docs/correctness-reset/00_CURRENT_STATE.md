# Chuzom Correctness Reset — 00. Current State (Phase 0 baseline)

**Status of this document:** Baseline + call-site inventory recorded from direct inspection.
Deep per-subsystem data-flow maps (accounting / enforcement / health / claims) are being
traced and will be folded in as sections §5–§8. **No production code has been modified.**

---

## §1. Baseline snapshot

| Item | Value |
|---|---|
| Commit | `d748d117f2bcf110cff24b79045a3f0598eaece5` (`v0.10.1-2-gd748d11`) |
| Delta vs tag `v0.10.1` | 2 commits, lint/CI-only (`fbcff1a`, `d748d11`) — no behavioral change |
| Working tree | clean except untracked audit docs + `uv.lock` (M) |
| Python (venv) | 3.11.15 (`.venv`); system 3.9.6 |
| uv | 0.11.23 |
| Source size | **105,615 LOC across 375 `.py` files** under `src/chuzom` |
| Test files | 391 under `tests/` |

### Dependency facts material to later phases
- Present: `pytest 9.0.2`, `pytest-asyncio 1.3.0`, `pytest-timeout 2.4.0`, `pytest-xdist 3.8.0`, `pytest-cov 7.1.0`, `aiosqlite 0.22.1`, `openai 2.24.0`, `structlog 25.5.0`.
- **MISSING (required by Phase 7):** `hypothesis` (property tests), `mutmut`/`cosmic-ray` (mutation tests), `pytest-benchmark`. These must be added as dev-deps before Phases 7–8 can execute.

---

## §2. Baseline test result — NOT deterministically green

Full suite (`uv run pytest -q --timeout=120`): **pytest exit code 1.**

- Approx outcomes from the progress stream: ~thousands passed, **160 skipped, 1 xfailed, 3 FAILED**.
- The 3 failures are all in `tests/test_zero_claude_bypass.py`:
  - `test_zero_claude_blocks_on_success`
  - `test_default_mode_blocks_self_contained`
  - `test_explicit_echo_mode_stays_advisory`
- **These pass when the file is run in isolation** (`pytest tests/test_zero_claude_bypass.py` → 8 passed). They fail only in the full run.

**Finding B0-1 (order-dependent test pollution).** The suite is not hermetic: at least these
three enforcement tests depend on state leaked by earlier tests (env vars, module-level
singletons, or on-disk `~/.chuzom` state). This directly threatens **Release Gate 20**
("complete test suite passes from a clean checkout") and undermines confidence in every
enforcement assertion, because a passing run and a failing run differ only by ordering.
Root-cause candidates to confirm in Phase 7: process-global env mutation in enforcement
hooks, shared `session_spend.json`/`enforcement.log` on disk, unreset module singletons.
No unit fix is valid until the pollution source is isolated (fixtures must reset global state).

---

## §3. Call-site inventory — cost / savings (raw sweep)

Distinct modules that **compute or record cost/savings** (each a candidate independent-truth
source to be collapsed into the canonical ledger in Phase 2):

| Module | Role (from sweep) |
|---|---|
| `router.py` | 2× `cost.log_usage()` (L2085 winning attempt, L2516 emergency fallback); `session_spend...record()` (L2133); `record_route(RouteLedgerRecord)` (L2172); `_failed_attempt_cost` accumulate (L1536+, escalation L2034+) |
| `cost.py` | canonical `log_usage`, usage SQLite, `get_savings_by_period`, `get_team_savings`, `_host_is_metered`, host prices |
| `session_spend.py` | `net_savings_usd`/`baseline_avoided_usd`/`real_dollars_avoided_usd`/`potential_savings_usd`/`realized_savings_usd`/`opus_equivalent_usd` (L316–369); `record()`, `mark_overridden` |
| `routing_quality.py` | `RouteLedgerRecord` JSONL ledger (`record_route`, L369) |
| `hooks/session-start.py` | weekly digest savings math (~L600–699) |
| `hooks/session-end.py` | own `HOST_INPUT/OUTPUT_PER_M` constants; `_net_session_line`; realized calc (L1364/1422); writes `savings_log.jsonl` |
| `hooks/enforce-route.py` | `mark_overridden` call (L1067) |
| `hooks/stop-enforce.py` | plain-text override detection (does NOT feed session_spend — to confirm §6) |
| `tools/admin.py` | `llm_savings`, `llm_session_spend`, `llm_team_report` |
| `team.py` | Slack/Discord/Telegram `saved_usd` payloads (L104/142/179); `get_team_savings` (L278) |
| `digest.py` | `simulate_without_routing`, `savings_pct` (L139–162) |
| `dashboard_data.py` | `savings_stats` JSONL table (L49); `WindowTotals.saved_usd` |
| `summary.py` | `savings_usd`/`savings_pct` (L65/204) |
| `statusline_hud.py` | `savings_pct` (L256) |
| `terminal_style.py` | `format_savings_bar`/`format_savings_card` (L171/285/329) |
| `retrospective.py` | `total_saved` sum (L172) |
| `route_server.py` | `_log_route_savings` → `savings_log.jsonl` (L92/132) |
| `observability.py` | cost/latency histograms (L288/292) |

**Preliminary structural finding B0-2 (distributed truth).** ≥18 modules independently touch
cost/savings; at least these maintain their own arithmetic rather than deriving from a single
source: `session-end.py` (own price constants), `session-start.py` digest, `summary.py`,
`digest.py`, `dashboard_data.py`, `retrospective.py`, `terminal_style.py`, `team.py`,
`statusline_hud.py`. This is the architectural condition behind the recurring accounting
findings and is the primary target of Phase 2.

---

## §4. Call-site inventory — override / escalation / health / storage / claims (raw sweep)

- **Override/realization:** `enforce-route.py:1067` (`mark_overridden`, tool-call path only);
  `stop-enforce.py` (plain-text path — strikes/log, wiring to be confirmed §6);
  `session-end.py:1364/1422` (`realized = gross - overhead`).
- **Escalation/fallback:** `router.py` `_failed_attempt_cost` (L1536), quality-escalation
  (L2034–2051, threshold/deadline env-gated L1546–1568), emergency BUDGET fallback (L1494+).
- **Provider-health sources (10 modules touch "health"):** `health.py` (HealthTracker),
  `router.py` (`is_healthy` at route time), `commands/doctor.py`, `hook_health.py`, `alerts.py`,
  `service.py`, `gateway.py`, `service_manager.py`, `classifier.py`, `config.py`.
  Divergence between `doctor.py` and `health.py` to be proven in §7.
- **Direct SQLite/JSONL writers (~20 modules):** `session_spend.py`, `dashboard_data.py`,
  `routing_report.py`, `route_server.py`, `budget_backend*.py`, `result_cache.py`,
  `idempotency.py`, `feedback.py`, `policy.py`, `policy_versions.py`, `retrospective.py`,
  `sidecar.py`, `tenant_policy_sidecar.py`, `discover.py`, `onboard.py`, `gateway.py`,
  `safe_config.py`, `budget.py`, `test_delta.py`. Source-of-truth vs cache classification in §8.
- **Public claims:** `README.md` + `scripts/capability_claims_baseline.txt` (46 lines,
  grandfather list). The `35–80% ... proven` claim and the baseline-exemption mechanism to be
  documented in §8.

---

## §5. Accounting data-flow map (first-hand confirmed)

### §5.1 The route → record path (`router.py`, direct read)
```
for attempt, model in chain:
    response = await dispatch(model)
    if gate_failed:                       # ~2016-2023
        _failed_attempt_cost += response.cost_usd   # 2022  "billable, rejected"
        continue                           # 2023  → skips ALL recording below
    if low_quality and can_escalate:       # ~2050-2075
        _failed_attempt_cost += response.cost_usd   # 2074  "billable, rejected"
        continue                           # 2075  → skips ALL recording below
    tracker.record_success(provider)                 # 2084
    await cost.log_usage(response, ...)              # 2085  ← WINNING response only
    ...
    _spend.record(cost_usd=response.cost_usd, ...)   # 2133  ← WINNING response only
    # later, ONCE:
    _actual = _final_cost + _failed_attempt_cost     # 2172  ← honest total
    record_route(RouteLedgerRecord(actual_cost_usd=_actual, ...))  # 2172  ← JSONL only
```

### §5.2 CONFIRMED accounting defects (file:line, first-hand)
- **AC-1 (=P0-1): rejected/escalated attempt cost never reaches user-facing spend.**
  `_failed_attempt_cost` (router.py:2022, 2074) is folded into `_actual` **only** at the
  `RouteLedgerRecord` write (router.py:2172), which lands in `~/.chuzom/routing_quality.jsonl` — a
  store **no user-facing surface reads** (§8.3). `cost.log_usage` (2085) and `session_spend.record`
  (2133) receive only the winning `response`. Result: on every quality-gated escalation or gate
  rejection, the `usage.db`/`session_spend` totals (which drive every dashboard) **undercount actual
  spend** by `_failed_attempt_cost`, and thus **overstate savings** by the same amount.
- **AC-2: `get_team_savings` lacks the metered gate that `get_savings_by_period` has.**
  `cost.py:2761` correctly sets `real_dollars_avoided_usd = saved_total if _host_is_metered() else 0`.
  `get_team_savings` (`cost.py:2857`) has no `real_dollars_avoided_usd` split and no `_host_is_metered`
  branch → the B-7 fix was applied to one sibling and not the other. Team/Slack/Discord/Telegram
  payloads (`team.py:104/142/179`) read `saved_usd` from this ungated function.
- **AC-3: `session-end.py` reimplements host pricing with its own stale constants.**
  `session-end.py:47-48` hardcodes `HOST_INPUT_PER_M=15.0`, `HOST_OUTPUT_PER_M=75.0` ("Opus 4.6"),
  computes baseline at L416 and L1544 from them, **never imports `cost.py`**, and **never gates on
  `_host_is_metered()`**. So the end-of-session summary — shown every session — is both mispriced
  (independent of `cost.py`'s corrected constants) and presents baseline-avoided as if real.

### §5.3 Independent-truth inventory (surfaces computing their own savings math)
| Surface | file:line | Reads-from | Own math? | Host-mode aware? |
|---|---|---|---|---|
| `cost.get_savings_by_period` | cost.py:2698 | usage.db | derives | **Yes** (2761) ✓ |
| `cost.get_team_savings` | cost.py:2857 | usage.db | derives | **No** ✗ (AC-2) |
| `session_spend` properties | session_spend.py:316-369 | in-session | own | partial (`real_dollars_avoided_usd` only) |
| `hooks/session-end.py` | 47-48, 416, 1544 | own JSONL | **own + stale prices** | **No** ✗ (AC-3) |
| `hooks/session-start.py` digest | ~600-699 | usage.db | own | partial |
| `admin.llm_savings` | admin.py (llm_savings) | get_savings_by_period | derives | **Yes** ✓ (the honest template) |
| `admin.llm_session_spend` | admin.py | session_spend | derives | **No** ✗ (labels potential/realized w/o caveat) |
| `team.py` payloads | 104/142/179 | get_team_savings | derives | **No** ✗ |
| `digest.py`, `summary.py`, `dashboard_data.py`, `statusline_hud.py`, `terminal_style.py`, `retrospective.py`, `route_server.py` | §3 | mixed | several own | mostly No |

**Canonical fix target:** collapse §5.3 into ONE aggregation layer over ONE append-only event
ledger that records **every** attempt (accepted + rejected + escalated + fallback) exactly once, with
`_actual` semantics as the only cost total, host-mode-aware labels centralized. `usage.db` becomes a
derived read-model; `routing_quality.jsonl`'s honest fields move into the canonical ledger.

### §5.4 Addendum (full accounting trace) — additional confirmed defects
The deep trace widened the defect set beyond AC-1..AC-3:
- **AC-4: ~10 independent, uncoordinated price-constant sets.** `session-end.py` (15/75 **stale, 3×
  inflation** vs current sonnet), `digest.py` (15/75, **mislabeled "Sonnet" but Opus values**),
  `dashboard_data.py` (15/75 duplicated twice in-file), `summary.py` (GPT-4o-anchored, latency-proxy —
  not a real token counterfactual), `tiers.py`, `receipt_store.py` ($5/$25), `savings_logger.py`
  (correct), plus `cost.py` `CLAUDE_RATES_PER_M`/`BASELINE_PRICING` (duplicate subset). Only
  `cost.get_savings_by_period` is metered-gated.
- **AC-5: dual-writer RACE on `savings_stats`.** `cost.import_savings_log` (async/aiosqlite) and
  `session-end.py::_sync_import_savings_log` (sync/stdlib) both drain `savings_log.jsonl`→`savings_stats`
  →truncate, **unlocked** — concurrent fire double-inserts. Also dual-writer on `claude_usage`
  (`cost.log_claude_usage` vs `session_spend._persist_to_claude_usage`).
- **AC-6: whole cost paths bypass accounting.** Emergency BUDGET fallback reaches only
  `cost.log_usage` (not `session_spend`/ledger); **semantic-cache hits bypass ALL cost accounting**;
  pre-dispatch denials write only `cost_usd=0` audit rows.
- **AC-7: dead/broken accounting surfaces.** `get_savings_by_task_type` (zero callers),
  `terminal_style.format_savings_*` (orphaned), `statusline_hud` (`baseline_cost` never supplied → always 0),
  `retrospective.py` (reads nonexistent `saved_usd` key → **permanent $0 display bug**),
  `calc_savings` (hardcodes `baseline="opus"` despite task-aware docstring).
- **Positive:** `cost.log_usage` already stores a task-aware baseline (`baseline_model`,
  `potential_cost_usd`, `saved_usd` columns) via `_get_baseline_for_task` (`cost.py:712`); only
  `routing_report.py` consumes it. The canonical ledger should carry this per-attempt so all surfaces
  read one honest baseline. `admin.llm_savings` remains the honest label template.
These add coverage under INV-COST-004 (single total), INV-COST-006 (metered gate everywhere),
INV-COST-003 (dedup/no-double-count for the `savings_stats` race), and motivate deleting AC-7 dead code.

## §6. Enforcement / override / hook-overhead map

### §6.1 Enforcement mode × blocklist (default = `smart`, `enforce_config.py:38`)
Blocklists (`enforce-route.py:71-86`): `_BASE_BLOCK_TOOLS={Bash,Edit,MultiEdit,Write,NotebookEdit}`;
`_QA_ONLY_BLOCK_TOOLS={Glob,Read,Grep,LS}`; `_QA_TASK_TYPES={query,research,generate,analyze}`.

| Mode | Read/Grep/Glob/LS blocked (QA types) | Bash/Edit/Write blocked | Notes |
|---|---|---|---|
| `off`/`shadow`/`advise` | No | No | `auto-route.py` writes `write_pending=False` (3196-3217) |
| `suggest` | No (soft = log-only) | No | but `write_pending=True` (3218-3229) → stale pending can bite later turns |
| **`smart` (DEFAULT)** | **Yes** | No (code types keep read tools) | QA types get full blocklist |
| `hard` | Yes | Yes | full blocklist all task types |
| `strict` | Yes | Yes | + disables all escape valves/auto-pivot |

### §6.2 Capability dead-end (anti-goal #1) — CONFIRMED, with a worse-than-thought tier case
Reproducing condition: mode ∈ {smart,hard,strict} AND task_type ∈ QA AND first turn needing an
**unseen** file's content.
- Chain: prompt→QA directive names completion door `llm`/`llm_query` (`auto-route.py:3230-3271`);
  Claude's `Read/Grep/Glob` blocked (`enforce-route.py:71-86`); block message tells Claude to pass
  `context=file_content` (`enforce-route.py:~1163`) — **circular**, since Read/Grep/Glob were what
  would produce it.
- The forced door set (`llm`, `llm_query/analyze/code/research/generate`) accepts only `prompt`,
  `context:str`, `system_prompt` — **no `files`/`paths` param** (`tools/text.py:448-456`). `llm_act`
  likewise (`tools/consolidated.py:75-83`).
- Only `llm_edit(task, files:list[str], ...)` reads files server-side (`tools/text.py:796-857`,
  `edit.py:25` 32 KB cap) — but it is (a) **undiscoverable**: needs exact paths while `Glob` is also
  blocked; (b) **semantically mis-signposted** (docstring says "code-edit… refactoring/bug fixes");
  (c) **not named** by the block message's remediation; and critically (d) **tier-gated off** under
  `CHUZOM_SLIM=core|routing` (present only in `CONSOLIDATED_TOOLS`, `tool_tiers.py`). Under those
  slims the dead-end is **absolute, zero escape hatch**.

### §6.3 Override accounting — two DISJOINT detectors (root cause of realized-savings overcount)
| | `enforce-route.py` `mark_overridden` (L1067) | `stop-enforce.py` `DIRECT_ANSWER` |
|---|---|---|
| Hook | PreToolUse | Stop |
| Detects | unrouted turn that completed via a native tool | plain-text answer with no tool call |
| Updates `session_spend`? | **Yes** (`overridden_turns`+1 → prorates `realized_savings_usd`, `session_spend.py:371-381`) | **No** — strikes counter + `~/.chuzom/enforcement.log` only |

Plus a **third** blind spot: the context-dependent-override branch (`auto-route.py:3273-3303`) sets
`write_pending=False` **unconditionally**, so those turns can never be counted as overrides at all.
Net: the two states that most look like "Claude silently did the work" (`DIRECT_ANSWER`,
context-dependent) never reduce `realized_savings_usd` → **systematic overcount**.

### §6.4 Hook token overhead (deadweight) — per `UserPromptSubmit`, `auto-route.py:3390-3397`
| Variant | file:line | Size | `write_pending` | Offload possible? |
|---|---|---|---|---|
| `advise` | 3204-3217 | ~104 tok | False | Never |
| `suggest` | 3218-3229 | ~51 tok | True | only via stale pending |
| `hard`/`smart`-else | 3230-3271 | **~446 tok** | True | Yes (drives blocking) |
| **context-dependent override** | 3273-3303 | **~227 tok** | **False (unconditional)** | **Never — by design** |

**Finding: guaranteed-deadweight class.** `_is_context_dependent()` (`auto-route.py:2154-2175`) is
biased toward True (its own docstring), so ordinary references ("this file", "it", "the repo") trip
it — injecting ~227 tokens every such turn with `write_pending=False` making offload structurally
impossible. A permanent per-turn tax with zero possible benefit, unmeasured in any savings surface.

### §6.5 Terminal states — most not wired to accounting
Distinct outcomes exist (ALLOWED / ALLOWED(soft/readonly/nongenerative) / SHAPE_OVERRIDE /
FS_EXEMPT / PENDING / PENDING EXPIRED / BLOCKED / BLOCKED(strict) / DELEGATE_ROUTE / AUTO-PIVOT /
OBSERVATION / ZERO_CLAUDE BLOCKED / mark_overridden / DIRECT_ANSWER). Only `mark_overridden` touches
`session_spend`. There is **no single enumerated terminal-state field** recorded per route — states
live as scattered log-string tags. (Directly motivates INV-ROUTE-004/005: one canonical terminal
state per route, recorded in the ledger.)

## §7. Provider-health divergence map

### §7.1 Health-source inventory
| Surface | file:line | Health source | Circuit state? |
|---|---|---|---|
| Router primary loop | `router.py:1604` `is_healthy` | `health.py` `HealthTracker` singleton (in-process) | Y |
| Router emergency loop | `router.py:2473` `is_healthy` | same singleton | Y |
| Failure/success recording | `router.py:2412/2427/2439` (primary), `2515` (emergency) | writes singleton | Y (asymmetric — §7.3) |
| `llm_health()` tool | `admin.py:372-413` → `status_report()` | same singleton | **Y — only external surface reflecting it** |
| **`chuzom doctor`** | `commands/doctor.py:595-1005` | hooks/config/usage-mtime/gateway `/healthz`/env-keys | **N — zero reference to health.py** |
| Gateway daemon `/route` | `route_server.py:41/59` | same router code, **own OS-process singleton** | Y but process-isolated |
| `migrations/001_create_chuzom_health.py` | — | creates `chuzom_health` table | **DEAD CODE — zero INSERT/SELECT anywhere** |

### §7.2 doctor↔router divergence — CONFIRMED and STRUCTURAL
- `doctor.py` never imports `chuzom.health`/`get_tracker`/`is_healthy` (full read + grep). Its
  pass/fail set (`doctor.py:993-1005`) can never receive a circuit-breaker entry.
- `HealthTracker` is **pure in-memory**; `doctor` is a fresh short-lived CLI process. So even adding
  `get_tracker()` to doctor would read an **empty** tracker, sharing zero state with the MCP-server
  process where routing runs. **Closing this requires an RPC/shared-store bridge or having doctor
  call `llm_health()`** — not a one-line import.
- The router's own diagnostic (`router.py:2553-2560`) tells users to run **`llm_health()`** for
  circuit status, not `doctor` — an in-repo admission of the split.
- **Concrete disagreement:** `openai` hits 2 failures → breaker trips (`config.py:369` threshold=2,
  30s cooldown); router skips it every request (`router.py:1605`); `chuzom doctor` in another terminal
  prints "✓ All checks passed. Chuzom is healthy." because keys/hooks/gateway are all fine.
- Fields: **only 2 of 11** spec-required fields present in doctor (`credentials_present`, degraded
  `gateway_reachable`). `circuit_state`/`recent_failure_count`/`rate_limited` live only in
  `llm_health()` as human-readable strings; `policy_allowed`/`router_eligible`/`ineligibility_reason`/
  `last_failure`/`last_success` are exposed as structured fields by **no** surface. Motivates
  INV-HEALTH-001/002/003.

### §7.3 Two new internal health defects
- **Emergency-loop failure asymmetry:** the BUDGET-fallback `except` (`router.py:2542-2549`) never
  calls `record_failure`; only the primary loop does (`router.py:2427/2439`). A provider failing
  *only* via the emergency path never trips its breaker, though the same `is_healthy` gate
  (`router.py:2473`) guards it.
- **Cross-process fragmentation:** MCP-server and gateway daemon each hold a separate `HealthTracker`;
  a provider tripped in one is not tripped in the other. Health truth is per-process, not global.

### §7.4 Fail-open vs fail-closed — GOOD (fail-closed)
Empty chain → `ValueError` (`router.py:3141-3148`); full exhaustion → `RuntimeError`
(`router.py:2603-2606`). No `except` swallows these into a silent Claude answer *within* `router.py`.
This is a genuine North-Star positive. (Correction to spec phrasing: `router_block_providers` does
not exist; the real filter is `block_providers` on `OrgPolicy`/`RepoConfig`, applied in
`router.py:493-521` + `712-721`. `tool_tiers.py` is tool-registration only, unrelated to provider
eligibility.)

## §8. Claims / benchmark / storage-topology map

### §8.1 Claims — the guard cannot see the claims that matter
`scripts/lint_capability_claims.sh` `CLAIM_RE` matches only absolute-guarantee **words**
(`guarantee(d)|prevents|never spends/exceeds|100%|fully enforced|proven|…`). It does **not**
match generic numeric savings language (`saves`, `%`, `35–80`, `50-100x`, `automatic`), and only
scans `README.md` + `.md` under `docs/Docs`, not `.py`.
- Structurally invisible to the guard (never candidates): `README.md:75` ("saves ~160,000 tokens/
  session"), `~131-165` (weekly $ tables, "~75% to Ollama"), `1064` ("70–80% savings… $200–800/yr").
- The `enforce-route.py:1233` runtime message "Routing saves 50–100x on this task" is in a `.py`
  f-string → out of scope entirely.
- **Grandfathered** (baseline.txt:43-46, matched by trimmed-text signature so never re-checked):
  `35–80% cost savings — proven` (L46), `guaranteed cost savings on every turn` (L44),
  `hard = guaranteed savings` (L45).
- Positive example (the model to generalize): `README.md:1335` `<!-- claim-ok: … verified by
  tests/test_zero_claude_bypass.py + …_sidecar_bypass.py (CHZ-AUD-005) -->` cites tests + ticket.
- CI: `.github/workflows/ci.yml:31-32`, no `continue-on-error` — guard is a real ratchet, but a
  ratchet that only stops *new guarantee-word* claims. **Directly motivates INV-CLAIM-001/002/003.**

### §8.2 Benchmarks — NO real control-group A/B exists
| Artifact | What it is | Real Chuzom-on-vs-off? |
|---|---|---|
| `bench/` (`python -m bench`) | Chuzom vs AlwaysCheap/AlwaysPremium/StaticChain on 10-prompt synthetic corpus | No — router-vs-router, tiny offline corpus |
| `digest.py:~120-175` `simulate_without_routing` | reprices real routed tokens at Sonnet/Opus rates | No — retrospective repricing |
| `test_delta.py` | manual before/after `usage.db` snapshot diff | No — **its own docstring admits** "Running benchmarks doesn't test the live router" |
| `bench/experiments/replay.py`, `analysis.py` | replay recorded cassettes through `cost.log_usage`; reconcile vs `_OPUS_PRICING` | No — fixed cassettes, same baseline table |

**Every savings number in the repo is a counterfactual repricing, not a measured A/B.** README's
"Benchmarks" cites 53 prompts while `bench/` states 10 — internal inconsistency. **This means the
"35–80% proven" claim has no reproducible control-group evidence** (Phase 8 must build one).

### §8.3 Storage topology — SoT vs cache
| Store | Writer | Class | Holds |
|---|---|---|---|
| `usage.db` tables (`usage`, `claude_usage`, `routing_decisions`, `savings_stats`, `codex/gemini_usage`, …) | `cost.py` (log_usage L664, log_savings L2384, …) | **SoT** | all completed calls + aggregate savings |
| `~/.chuzom/routing_outcomes.db` | `session_spend.py` `_persist()` | **SoT (durable)** | 1 row/session — exists *because* session_spend.json is wiped |
| `~/.chuzom/routing_quality.jsonl` | `routing_quality.py:147` `record_route` | **SoT, UNBOUNDED** — no SQLite import anywhere; grows forever; sole source for its fields | per-route chain diagnostics |
| `~/.chuzom/session_spend.json` | `session_spend.py:439` `_persist` | **cache** — reset each session-start | live counters |
| `~/.chuzom/savings_log.jsonl` | `route_server.py:134`, PostToolUse | **buffer** — truncated after import (`session-end.py:349`) | raw per-call savings awaiting import |
| `~/.chuzom/enforcement.log` | `stop-enforce.py:95` | **append-only log, no eviction** | direct-answer/enforcement events |
| `budgets.db` | `budget_backend.py` (BEGIN IMMEDIATE) | **SoT** | budget reservations |
| `result_cache.db`, `idempotency.db` | resp. | **cache** (explicit eviction/TTL) | dedup |
| `feedback.db`, `policy_versions.db` | resp. | **SoT** | routing events / versioned policy |

**Key structural facts for Phase 2:** (1) `usage.db` is already the closest thing to a canonical
store, but savings truth is split between it, `routing_outcomes.db`, `routing_quality.jsonl`, and
per-surface recomputation (§3). (2) `routing_quality.jsonl` — which the earlier audit showed holds
the *only honest* failed-attempt cost — is an **unbounded JSONL that no report reads**. The canonical
ledger should absorb this and become the single append-only event source, with `usage.db` a derived
read-model.

### §8.4 Test-infra gaps (Phase 7 blockers)
`hypothesis`, `mutmut`, `cosmic-ray`, `pytest-benchmark` — **all absent** from `pyproject.toml` and
the venv. A `performance` pytest marker exists but has no `pytest-benchmark` backing. Property-based
and mutation testing must be added from scratch.

---

## §9. Root cause (confirmed) — why eight audits kept finding new problems

The recurring findings are symptoms of **five architectural conditions**, each of which spawns a
whole *category* of findings. Patching a symptom site never removed the condition, so the next audit
found the same category at a different site.

| # | Architectural condition | Evidence | Finding category it generates |
|---|---|---|---|
| RC-1 | **Distributed accounting truth** — ≥18 surfaces compute/store savings independently; the honest total (`_actual`) lives only in an unread JSONL | §3, §5, §8.3 | inconsistent/false/overstated savings; rejected-cost undercount (AC-1) |
| RC-2 | **No single terminal-state / attempt record** — every attempt (esp. rejected) is not a first-class recorded event; cost recording is winner-only | §5.1, §6.5 | missing attempt costs, unclassifiable spend |
| RC-3 | **Two disjoint override detectors + a third silent branch** — only `mark_overridden` feeds accounting | §6.3 | realized-savings overcount |
| RC-4 | **Two disjoint (and per-process) health signals** — doctor never sees the router's in-memory breaker | §7 | doctor/router disagreement; under-tripped breakers |
| RC-5 | **Claims/benchmark decoupled from evidence** — guard blind to numeric claims + grandfathering; no control-group harness | §8.1, §8.2 | unsupported "proven" claims |

Cross-cutting enabler: **RC-0, a non-hermetic test suite** (§2, B0-1) — order-dependent failures mean
accounting/enforcement regressions can pass CI by luck, so defects survive to the next audit.

**Design consequence (drives Phases 2–8):** the reset must (a) introduce ONE append-only,
attempt-level execution ledger as the single semantic source of truth [RC-1, RC-2], (b) route every
override detector and every terminal state into it [RC-2, RC-3], (c) unify health so doctor and router
read one snapshot [RC-4], (d) replace claim grandfathering with an evidence registry fed by a real
control-group benchmark [RC-5], and (e) make the suite hermetic so every invariant is proven on a
clean checkout [RC-0]. Patching symptom sites is explicitly out — per the completion standard, the
goal is to make the *next* audit boring.

---
**Phase 0 status: COMPLETE.** All four subsystem maps (§5–§8) folded in; root cause established;
no production code modified. Proceed to Phase 1 (executable contract) → Phase 2 (canonical ledger).
_(The background accounting agent may return an even fuller §5.3 surface inventory; it will be
reconciled in as an addendum but does not change the confirmed defects AC-1..AC-3.)_
