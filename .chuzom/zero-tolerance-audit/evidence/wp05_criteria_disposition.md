# WP-05 — disposition of the five acceptance criteria

Date: 2026-08-12. Commits: `1919b5d` (baseline unification), plus the
subscription/provenance change that follows it.

The criteria are pre-registered and immutable. Four are met literally. One is met
by interpretation, recorded here in full because an interpreted criterion is
exactly the kind of thing a re-audit must be able to challenge.

---

## 1. Query failure distinguishable from zero at the type level — MET (pre-existing)

Landed earlier in `09832b1`. `get_savings_summary()` returns
`provenance: "unknown"` plus `Measured.unknown(...)` on query failure, versus
`provenance: "measured"` and `Measured.measured(0.0)` on a genuine zero.
Pinned by the immutable asset `tests/economics/test_unknown_not_zero.py`.

## 2. Only one baseline policy symbol exists — MET

`pricing.SAVINGS_BASELINE_MODEL = "claude-opus-5"`, reached through
`savings_baseline_model()` / `savings_baseline_rates()`.

Three policies previously coexisted, two of them introduced to override the
other (`cost._get_baseline_for_task` tiered; `savings_logger`'s per-complexity
table; the dashboard/session-end flat rate). On a QUERY call the first credited
Haiku ($1/$5) and the second Opus ($5/$25) — 5x apart on the identical call.

The tiered policy is **deleted**, not re-pointed. Owner decision, 2026-08-12: the
honest counterfactual is what the user would actually have spent, and a
subscriber runs their top model rather than hand-picking a cheaper Claude per
prompt. Consequence accepted knowingly: reported savings on query traffic rise
~5x relative to the tiered policy.

Guarded by `tests/economics/test_single_baseline_policy.py`, including an AST
check that no module outside `pricing.py` binds a `*BASELINE* = "claude-…"`
literal, an explicit allowlist for the two baselines that are legitimately
different (`router._BASELINE_COMPLETION_MODEL`, a quality comparator;
`commands/test.py BASELINE`, a benchmark reference), and a staleness check on
that allowlist.

## 3. `session-end.py` renders one figure, not two disagreeing ones — MET BY INTERPRETATION

**This is the interpreted one. Owner decision, 2026-08-12.**

The criterion targets two figures that *disagree*. They did: the session panel
derived savings from `_host_baseline` (Opus rates) while the cumulative panel
read stored `saved_usd` rows written against a different baseline. Same word,
different arithmetic, no way for a reader to tell.

After criterion 2 both derive from the one policy — `_format_routing_section`
via `cost._HOST_*_PER_M`, `_format_cumulative_section` via
`dashboard_data.query_window` → `_BASELINE_MODEL`, both resolving to
claude-opus-5 at $5/$25. They no longer disagree.

Two figures remain on screen. They differ by **window**, not by derivation:
`this session` versus `today` / `lifetime`, each labelled. The judgement
recorded is that two correctly-labelled windows are not the defect this
criterion names, and collapsing them would remove information users rely on
(the sparkline, period grid and yearly projection) without removing a
disagreement.

**A re-auditor who reads the criterion literally should mark this NOT MET.**
That is a legitimate reading. What must not happen is for it to be scored met
without this note being read.

## 4. A subscription user is never shown a cash-savings figure — MET

`_is_subscription_mode()` (fails **closed** to pay-per-token: an unreadable
config must not suppress a cash figure a paying user is entitled to). In
subscription mode the routing panel reports **quota preserved** in tokens and
drops the `$actual / $baseline / % saved` cash framing.

Scope boundary, deliberate: actual spend on external paid providers is still
shown. That is money genuinely leaving the account, and hiding it would
understate what routing costs. What is suppressed is a dollar figure presented
as money routing *saved* a subscriber, which README already disclaims —
"on a Claude Pro/Max subscription the value is quota runway, not cash".

## 5. Every displayed number carries measured | estimated | unknown — MET, and it reads `estimated`

`_baseline_provenance()` returns `measured` only when the savings baseline has a
real calibration profile. It does not have one: `INITIAL_CALIBRATION` covers
`claude-sonnet-4-6` alone, so the baseline's output-token count comes from
`_LEGACY_FALLBACK_OUTPUT`. The panel therefore renders **`estimated`**.

Owner decision, 2026-08-12: tag it `estimated` rather than stretching `measured`
to cover list-price arithmetic over a projected token count. Most surfaces will
read `estimated` until the calibration corpus covers more than one model — which
is the true state, and is tracked as an open finding (calibration coverage).

---

## Defects surfaced while landing this WP

All four share one shape: **a zero that renders as data rather than as unknown.**

1. `_claude_cost` is keyed by family alias, so a full model ID missed the table
   and returned `0.0` silently → zero baseline → **negative** savings.
2. `LATEST_OPUS_MODEL` lagged at `claude-opus-4-8` while `pricing` already
   priced `claude-opus-5`, against its own "bump when a newer Opus ships" note.
3. `calibration._lookup_pricing` returned zero rates for Opus → `predict_cost`
   returned `0.0` → auto-route silently fell back to its legacy static map and
   re-rendered the exact `$0.0005` the Cat-F work had removed. No error, and a
   plausible number. Caught only because the guarding test's docstring named
   that constant as the old broken value — without that sentence it ships.
4. The calibration corpus covers exactly one model, so any baseline change
   degrades projections silently. Open finding; feeds WP-07's coverage metric.

Item 3 is the one to carry into WP-16: the failure was invisible, the output was
plausible, and the only thing that caught it was a comment.

---

## A near-miss worth recording

The first implementation of criterion 4 read `chuzom_claude_subscription` from
ambient config inside `_format_routing_section`. That made the panel's output
depend on the developer's own config: three existing cash-rendering tests
(`test_dash5_saved_definition`, `test_session_report` ×2) pass on a
pay-per-token machine and fail on a subscriber's. This machine is
`subscription=True`, so they failed here.

It is the same defect class fixed earlier the same day in `6edffc5`, where
`tests/audit/test_provider_matrix.py` read the developer's model registry and so
passed in CI and failed locally. Reintroduced within hours of being fixed —
because the ambient read is the natural way to write it, and nothing in the
codebase pushes back.

Fixed by making `subscription` an explicit parameter (`None` = detect, which is
what the hook passes) and pinning the mode in the three tests that assert cash
rendering.

Recorded here rather than only in the commit message because two independent
instances in one session is a pattern, not a coincidence. Added to WP-14 as a
general sweep: any test whose verdict depends on host state — installed models,
config flags, env, HOME contents, clock — is not a gate. **A CI-only green is
not evidence when the gate reads the host.**
