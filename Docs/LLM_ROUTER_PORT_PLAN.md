# LLM-Router ← Chuzom Routing Port — Master Working Plan

**Goal:** Upstream Chuzom's distinctive *routing decision* logic and its *observability
surfaces* (per-prompt "it's working" signal + session-end dashboard) into the public
`ypollak2/llm-router` (`llm-routing` on PyPI), **without** dragging in Chuzom's
enterprise/product surface (dashboard server, admin API, control plane, lineage,
budget backends, MCP product tools, media gen).

Both repos are MIT and same author, so attribution is trivial. `llm-router` is the more
mature *engine* (v10.x, 119 releases, 1900+ tests, RouterArena #8); Chuzom (v0.7.6,
~95K LOC) is a superset product. This is an **extract + reconcile** job between siblings,
not a from-scratch port.

---

## Guiding principles

- [ ] **Port decision modules, not the executor.** `router.py` is entangled with
      `identity / rbac / audit / quota_envelope / budget / idempotency / lineage / tracing`.
      Copy the *decision* logic (`classify`, `chain_builder`, `dynamic_routing`, `profiles`,
      `signals`), let llm-router's existing engine consume it.
- [ ] **No hardcoded provider/model literals** in ported decision code (Chuzom rule — see
      `classify.py` docstring). Everything resolves through the registry/profiles.
- [ ] **Offline-safe / fail-soft.** Every ported path falls back to a static chain or a
      plaintext render; routing/observability must never block the host.
- [ ] **Optional heavy deps.** `rich` stays optional with a plaintext fallback
      (mirror Chuzom's `HAS_RICH_DASHBOARD` try/except).
- [ ] **Gate product-specific panels.** Claude-subscription-% / "vs Sonnet" multiplier are
      opt-in, not default (a user with only Ollama + OpenRouter must still get a useful summary).
- [ ] **One PR per slice**, each with ported tests + changelog + golden decision snapshots.
- [ ] Structure ported code as a self-contained `llm_router/adaptive/` subpackage so it
      *could* later become a shared `routing-core` both repos depend on (kills future drift).

---

## Integration model (decision)

- **(A) Upstream select capabilities** into llm-router's engine as `llm_router/adaptive/`.
  Incremental, reviewable, low-risk. ✅ **Recommended — start here.**
- **(B) Shared `routing-core` package** both repos import. Permanent single-source-of-truth,
  but a big refactor of both. **North star, not now.** Build slices in (A) so they're
  extractable into (B) later.

---

## PHASE 1 — Ground-truth diff — ✅ DONE (2026-07-08)

**Finding: the two repos are the same codebase lineage** (llm-router `llm-routing` v10.1.5,
186 modules; Chuzom `chuzom-router` v0.7.6, 337 modules). Module names + line counts line up
(`chain_builder.py` identical 162L; `status-bar.py` identical 414L; `dashboard/server.py`
1288 vs 1289). So this is a **sync of the delta**, not a port to a stranger.

Remaining Phase-1 follow-ups:
- [x] Ran Chuzom's deterministic `classify_signals()` over the corpus + a 15-item labeled probe.
- [ ] Diff the **diverged-but-present** modules (below) to decide sync vs leave-alone.

### Decision-diff results (2026-07-08)

- `classify_signals()` runs standalone, 0-cost/no-network. **Hot-path rate 80% (corpus) /
  86% (probe)** — matches the ~80% design claim. Task-type agreement **93%**; the single miss
  *escalated* (not confident), so the LLM classifier would catch it. Decisions are sound.
- **Scoring is identical in both repos** — intent×3, topic×2, format×1, confidence threshold 2.
- **But llm-router already has this logic** — as `score_categories()` / `classify_prompt()` /
  `classify_complexity()` inside `hooks/auto-route.py`. It is **not importable** by `router.py`,
  the gateway, or MCP tools. llm-router's regex tables are actually the **fuller, live-tuned**
  source (25 category-blocks incl. `coordination` + arena fast-paths); Chuzom's `classify.py`
  carries a cleaned 6-category subset extracted from that hook.

**⇒ Slice 1 is a refactor-to-library, not a capability import.** Extract llm-router's OWN hook
classifier into an importable module, using Chuzom's `classify.py` as the structural blueprint.
Do NOT overwrite llm-router's richer tables with Chuzom's subset. Value = reuse (router /
gateway / tools gain the 0-cost classifier) + kill the hook's duplicate copy. Medium value
(architecture/reuse), not a routing-quality gain.

**Genuinely NEW capabilities (unchanged by this diff):** `subscription_local_routing.py`,
`signals/pii`, `surface_status.py`, rich session-end (`summary.py` + `ui/session_summary.py`),
`quota_routing.py`, `cache/classification.py`, `enforce_config.py`.

### Capability matrix (verified by file presence + line counts)

**MISSING in llm-router → real port targets:**

| Module | Slice | Note |
|---|---|---|
| `classify.py` | 1 | deterministic signal classifier — llm-router has only the *LLM* `classifier.py`. Port **additively** (hot path in front of the LLM classifier) |
| `signals/{base,keyword,pii}.py` | 6 | pluggable signals; **pii → force local** |
| `subscription_local_routing.py` | 3 | cost-inverted profile |
| `quota_routing.py` | 4 | quota-pressure decisioning (llm-router has partial `quota_tracker.py`) |
| `enforce_config.py` | 3 | enforcement config (llm-router has `enforce-route.py` hook + `policy.py`) |
| `cache/classification.py` (+ `cache/store.py`) | 5 | classification cache |
| `summary.py` | 0 | rich session-end content model (headline/sparkline/tiers/inversions/PII/punchline + markdown) |
| `surface_status.py` | 0 | cross-surface "it's working" (3 renderers) for hosts w/o a statusline API |
| `ui/session_summary.py` (+ `status_premium`, `status_spinner`) | 0 | 2-panel rich dashboard + 14-day chart |

**ALREADY PRESENT → do NOT port (sync a diff at most):**
`classifier.py` (306 vs 322), `chain_builder.py` (identical), `semantic_cache.py`,
`result_cache.py`, `quota_tracker.py`, `status-bar.py` (**identical — per-prompt signal
already exists**), `statusline_hud.py`, `discover.py`, `budget.py`, `claude_usage.py`.

**DIVERGED-but-present → Phase-1 follow-up diff before deciding:**
`dynamic_routing.py` (+69L in Chuzom), `providers.py` (+111L), `profiles.py` (+65L),
`policy.py` (+15L), `hooks/session-end.py` (+419L richer in Chuzom).

> **Not ported (stays Chuzom-private):** everything under `enterprise/`, `control_plane/`,
> `lineage/`, `budget_backend*`, `rbac_routing`, `audit_routing`, `identity`, `tenant_*`,
> `invoice_reconciliation/`, `frameworks/`, `gateway*`, `agents/` governance.

---

## PHASE 2 — Extraction boundary

- [ ] For each candidate module, map its import graph; tag each dep:
      **portable** / **needs-thin-adapter** / **enterprise-only → stub**.
- [ ] Write the adapter interface llm-router provides to the ported code
      (config accessor, provider registry, usage-log writer, health snapshot).
- [ ] **Exclude list (never enters public repo):** `enterprise/`, `admin_api.py`,
      `control_plane/`, `dashboard/` (server/tui), `lineage/`, `budget_backend*`,
      `tools/` (MCP product), `media.py`, `rbac_routing`, `audit_routing`, `identity`,
      OAuth/claude-usage scrapers.

---

## PHASE 3 — Port in value-ordered slices (one PR each)

### Slice 0 — Observability surface *(do first: low-risk, self-contained, highest "feel" ROI)*

Chuzom's proof-of-work surfaces are **pure consumers of a shared append-only event log**
(`~/.chuzom/savings_log.jsonl` + `usage.db`), decoupled from the router core.

- [ ] **Event schema.** Define/confirm one appended record per route:
      `host, model, task_type, complexity, method, in_tok, out_tok, estimated_saved, ts`.
      Map onto llm-router's `~/.llm-router/usage.db`.
- [ ] **Per-prompt signal (UserPromptSubmit hook):** ⚠️ llm-router **already has**
      `status-bar.py` (identical) + `statusline_hud.py`. Do NOT re-port those.
  - [ ] Port ONLY `surface_status.py` → `SurfaceStatus` + 3 renderers
        (`compact_line`, `terminal_title`, `notification`) — for hosts *without* a statusline
        API (opencode, clawcode, plain terminals). Wire it as a fallback renderer.
- [ ] **Session-end dashboard (Stop hook):** the main observability delta.
  - [ ] Port `summary.py` content model: headline savings, sparkline, tier histogram,
        per-provider cost, routing inversions, PII-forced-local catches, top routes, punchline.
  - [ ] Port `ui/session_summary.py` rich two-panel + 14-day activity chart (rich optional).
  - [ ] Port `summary.render_markdown()` for logless/CI contexts.
  - [ ] Port `hooks/session-end.py` entry, **gating** subscription-% / quota-timeline panels behind a flag.
- [ ] Wire both into llm-router's existing `.claude/hooks` (+ `.codex-plugin`, `.factory-plugin`).

### Slice 1 — Extract the signal classifier into a library (refactor, not import)
> Phase-1 verified: llm-router already scores signals inside `hooks/auto-route.py`
> (`score_categories`/`classify_prompt`), but it's not importable. Its regex tables are the
> richer, live-tuned source — **keep them**. Use Chuzom's `classify.py` only as the module shape.
- [ ] Create `llm_router/adaptive/classify.py` with Chuzom's clean sync API
      (`classify_signals()`, `ClassifyPolicy`, `ClassifySignal`, confidence gate).
- [ ] Move llm-router's **existing** hook tables + `score_categories`/`classify_complexity`
      into it verbatim (don't substitute Chuzom's 6-category subset).
- [ ] Repoint `hooks/auto-route.py` to import from the module (kill the duplicate copy).
- [ ] Expose the 0-cost classifier to `router.py` / gateway / MCP tools: confident signal →
      use as-is (~80%, 0-cost); ambiguous → escalate to the existing LLM `classifier.py`.
- [ ] Golden test: hook decisions before == after the extraction (byte-for-byte on the corpus).

### Slice 2 — Dynamic chain builder (C2)
- [ ] Port `chain_builder.py` + `dynamic_routing.py`; hook into llm-router's provider discovery.
- [ ] Preserve free-first invariant, score floor, min-chain-length, offline→static fallback.

### Slice 3 — SUBSCRIPTION_LOCAL profile (C3)
- [ ] Port as a new policy; wire config (`*_SUBSCRIPTION_PROVIDER`, `*_INTERNAL_PROVIDERS`).

### Slice 4 — Quota-pressure reorder (C4)
- [ ] Port the *decision* half of `quota_routing.py` (drop envelope/enforcement plumbing).

### Slice 5 — Caches (C5)
- [ ] Port classification cache; then semantic + result cache (optional embedding dep gated).

### Slice 6 — Signals framework (C6)
- [ ] Port `signals/` incl. PII→force-local; surface catches in the session-end dashboard.

---

## PHASE 4 — Config & docs reconcile

- [ ] Map `CHUZOM_*` env vars → llm-router names; document precedence.
- [ ] Unify policy YAML (Chuzom `policies/standard.yaml` ↔ llm-router `policies/`).
- [ ] README: new capabilities, the observability screenshots, enable/disable flags.
- [ ] Preserve SPDX headers; add `NOTICE` crediting Chuzom.

---

## PHASE 5 — Guardrails (permanent, prevents re-drift)

- [ ] Golden decision snapshots committed (prompt → expected chain) for the shared corpus.
- [ ] RouterArena re-run to confirm no routing-quality regression.
- [ ] CI job that fails on golden-snapshot drift.

---

# QA STRATEGY — how we cover everything

Reuse Chuzom's existing pytest marker scheme verbatim so live tests stay opt-in:
`requires_ollama`, `requires_api_keys`, `requires_codex`, `slow`, `performance`,
`integration`, `unit`. Default `addopts` deselect `slow / requires_ollama /
requires_api_keys` — CI runs the fast tier; live tiers run on demand / nightly.

### Layer 1 — Unit (fast, hermetic, always in CI)
- [ ] Port each slice's Chuzom unit tests; adapt imports to `llm_router.adaptive`.
- [ ] Classifier: table-driven cases per category (query/code/research/analyze/generate)
      + complexity tiers; assert deterministic hot-path fires without any LLM call (mock provider).
- [ ] Chain builder: assert free-first ordering, score floor, min-length, offline→static.
- [ ] SUBSCRIPTION_LOCAL: assert order flips on complexity.
- [ ] Renderers: feed synthetic log records → assert compact_line / status-bar strings +
      session-end markdown contain expected fields (no rich needed — test `render_markdown`).

### Layer 2 — Golden decision tests (anti-drift, the key regression guard)
- [ ] Freeze `corpus → {task_type, complexity, chain}` snapshots; diff on every PR.
- [ ] Any intentional change = reviewed snapshot update; unintentional = CI fail.

### Layer 3 — Integration (mocked providers, in CI)
- [ ] Full path: prompt → classify → chain build → executor(mock) → **log record written**
      → status line reflects it → session-end dashboard aggregates it. One test, real wiring.
- [ ] Fallback: mock provider #1 raises (rate-limit / auth / content-filter) → assert
      walk to #2, and that the inversion shows up in the session summary.
- [ ] Offline: discovery empty → assert static chain still returned (never blocks).
- [ ] Malformed log line → dashboard degrades to plaintext, doesn't crash the hook.

### Layer 4 — Live / E2E (`requires_ollama` / `requires_api_keys`, opt-in + nightly)
The "see everything just works" tier. Uses your real local models
(`qwen2.5-coder:7b`, `hermes3:8b`) and, when keys present, one paid provider.

- [ ] **Live routing battery** (`requires_ollama`): send a labelled prompt set —
      simple query, code gen, research, complex analysis — through the *real* router;
      assert each (a) routed to the expected tier, (b) returned a valid non-empty response,
      (c) appended a correct `savings_log` record.
- [ ] **Live observability check:** after the battery, invoke the UserPromptSubmit hook →
      assert the status line renders and names the last routed model; invoke the Stop hook →
      capture the session-end dashboard → assert it lists the routed calls, a plausible
      savings number, tier distribution, and top routes.
- [ ] **Live failure injection:** kill/stop Ollama mid-battery → assert fallback to next
      available provider (or graceful "all local down" path) and that health flips in the
      status line + an inversion appears in the summary. Restart → assert recovery.
- [ ] **Latency budget** (`performance`): classifier hot path < a few ms with no network;
      session-end dashboard renders < 100ms with no network (Chuzom's stated budget).
- [ ] **Cross-host smoke:** run the same battery under Claude Code hook, Codex, Gemini CLI
      wiring; assert each host surfaces the signal (statusline / compact_line / notification).

### Layer 5 — Benchmark regression (nightly / pre-release)
- [ ] RouterArena submission re-run; assert rank/score not worse than the pre-port baseline.
- [ ] Savings sanity: end-to-end estimated-savings % on the corpus within expected band.

### Layer 6 — CI gates (what must be green to merge)
- [ ] Fast unit + integration + golden snapshots on every PR.
- [ ] `requires_ollama` live battery on a self-hosted/nightly runner.
- [ ] Coverage gate on `llm_router/adaptive/**`.
- [ ] Lint/type (ruff/mypy) matching llm-router's config.

### Manual live smoke checklist (per slice, before tagging a release)
1. Fresh install in a throwaway env; run 5 representative prompts.
2. Watch the per-prompt status line change model/tier each prompt.
3. End the session; read the dashboard — numbers add up, no crash without `rich`.
4. Disconnect network; repeat — routing falls back, dashboard still renders.
5. Confirm no Chuzom-private surface leaked (grep the built wheel for exclude-list modules).

---

## Definition of done (per slice)
- [ ] Ported code + adapted tests green in fast tier.
- [ ] Golden snapshots added/updated.
- [ ] One live-tier test exercising it end-to-end.
- [ ] Changelog + README section.
- [ ] No exclude-list dependency pulled in (verified by import-lint).

## Top risks
- Leaking private/enterprise surface into the public repo → Phase 2 boundary + wheel grep.
- Type/config impedance between the two engines → adapter layer, caught by integration tests.
- Re-drift over time → golden snapshots + north-star shared-core (B).
- Product-specific panels misleading generic users → gate behind flags, default off.
