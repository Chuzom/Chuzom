# 1.0 Cutover — Step 4 Migration Plan (BREAKING · cut as 0.10.0)

> Status: **PLAN ONLY — no code changes.** Steps 1–3 (consolidated tier, enforce
> door-naming, `DEPRECATED_TOOLS` registry) are landed and non-breaking. This doc
> specifies the breaking step so it can be reviewed and scheduled deliberately.
> Nothing here executes until explicitly approved.

## 1. Objective

Make the collapsed ~11-door surface the product's real surface: register only the
front doors by default, and stop exposing the ~67 legacy `llm_*` / `chuzom_agent_*`
MCP tools. This realises the North Star's "one obvious door per capability" and cuts
the ~8,000-token tool-schema injection that degrades routing accuracy.

## 2. The de-risking decision (read this first)

There are two ways to "remove" a legacy tool. They differ enormously in blast radius:

| Approach | What happens to `llm_query` the Python function | Test blast radius |
|---|---|---|
| **A. Un-register (recommended)** | Stays importable in `tools/text.py`; the `llm` door dispatches to it. Only its `@mcp.tool()` registration is dropped. | ~57 files |
| B. Hard-delete | Function deleted; doors inline the logic. | 400+ files + logic rewrite |

**Recommendation: Approach A.** The doors already call the legacy functions internally
(see `consolidated.py`), so the functions are the implementation, not dead weight.
Un-registering them removes them from the MCP surface (the user-visible goal) while
keeping the ~14 test monkeypatch targets valid. "Collapsing 73→11" is about the
*exposed tool surface*, not about deleting working code. Approach B buys nothing a
user can observe and multiplies risk.

## 3. What is removed vs. kept (Approach A)

**Kept & registered (the default surface):** the 11 `CONSOLIDATED_TOOLS` doors —
`llm`, `llm_act`, `chuzom_status`, `chuzom_admin`, `chuzom_session`, `llm_route`,
`llm_image`, `llm_audio`, `llm_edit`, `chuzom_agent_start_session`, `chuzom_agent_route`.

**Kept as importable functions, NOT registered:** every tool in `DEPRECATED_TOOLS`
(the 5→door map) — `llm_query/analyze/code/research/generate`, `llm_delegate`, the
observability set, the config set, the simple agent-lifecycle set.

**Removed outright:** the `CORE_TOOLS` (4) and `ROUTING_TOOLS` (12) tiers and their
tests — they become dead once `consolidated` is the default. `off` (register-all)
stays as an escape hatch for one release, gated behind `CHUZOM_SLIM=off`, then removed
in 0.11.

## 4. Test migration (measured, not guessed)

644 legacy-name references across the suite, categorised by how they break:

| Cat | Pattern | Count | Under Approach A |
|---|---|---|---|
| A | `monkeypatch.setattr("chuzom.tools.X.llm_query", …)` / direct import | ~14 unique targets | **No change** — function still there |
| B | MCP-dispatch string literals (`expected_tool="llm_query"`, `mcp__chuzom__llm_query`) | ~25 unique | Map to door via `door_for_tool()`; update fixtures |
| C | Tool-set / registration assertions (`CORE_TOOLS`, `len(registered)==41`, tier_summary) | ~32 files | Rewrite expected sets to the 11 doors; delete CORE/ROUTING tests |
| D | Already import from `consolidated` | 1 file | No change |

Net: **~57 files** need edits (B+C), the rest ride on the un-registration invariant.

Strategy for B: the `enforce-route` hook already routes via `door_for_tool()` (step 2/3),
so production is covered; only test *fixtures* that hardcode `expected_tool` need the
door name. A single helper (`door_for_tool`) drives both.

Strategy for C: these encode the old tool count/names. Replace with assertions against
`CONSOLIDATED_TOOLS`. This is where a `pr-test-analyzer` / `test-writer-fixer` pass earns
its keep — mechanical but must be verified, not sed-blind.

## 5. Sequencing — each sub-step its own gated slice

1. **4a — Flip the default tier.** Change the `chuzom_slim` config default `off`→`consolidated`
   (locate in `get_config()`). Land with C-category test updates in the same commit so the
   suite stays green. *This is the observable breaking change.*
2. **4b — Un-register legacy tools.** Remove the `@mcp.tool()` decorators from the legacy
   functions (keep the functions). Update B-category fixtures. Registration-count tests now
   assert 11.
3. **4c — Delete CORE/ROUTING tiers.** Remove `CORE_TOOLS`, `ROUTING_TOOLS`, their branches
   in `make_should_register`/`tier_summary`, and their tests.
4. **4d — Docs & deprecation notices.** README tool table → the 5 doors; `DEPRECATED_TOOLS`
   drives a one-line "use `llm` instead" notice for anyone importing an old name.

Each sub-step must pass the full CI-clean gate (the same one used for steps 1–3, with the
2 known #148 failures the only allowed reds) before the next begins.

## 6. Rollback

`CHUZOM_SLIM=off` restores the full surface through the whole 0.10 line (kept as the
escape hatch). If 4a regresses routing, revert the single default-flip commit — 4b/4c are
independent and additive-to-remove. Because the functions are never deleted (Approach A),
no behaviour is lost, only exposure.

## 7. Release framing

Cut as **0.10.0** — a deliberate breaking minor. Changelog leads with the surface change,
the `CHUZOM_SLIM=off` escape hatch, and the door-mapping table from `DEPRECATED_TOOLS`.
Not a patch, not an autonomous sweep.

## 8. Open decisions for the user

- **Approach A vs B** — plan assumes A (un-register, keep functions). Confirm.
- **Escape hatch lifetime** — keep `CHUZOM_SLIM=off` for all of 0.10 (recommended) or drop it immediately?
- **Media/fs doors** — `llm_image/audio/edit` stay as-is in 0.10; fold into `llm_media`/`llm_fs` later, or now?
- **Who drives the C-category rewrite** — a verified `test-writer-fixer` pass, or hand-migrate for control?
