# 07 — ECONOMICS AUDIT (RED-2)

> Target: `c2c28821f690f7cbda42b46da06fc36ef77d816e` / tag `v1.1.1`, clean worktree,
> `.venv-audit/bin/python` (3.11.15) only. Mandate: savings, cost accounting, telemetry
> integrity. Evidence standard per `00_AUDIT_BASELINE.md` §25: PROVEN / STRONG EVIDENCE /
> SUSPICION / NOT TESTED.

## ⚠️ Read this first: auditor-caused production incident

During construction of a synthetic reproducer for RED2-02, I corrupted the user's REAL,
PRODUCTION `~/.chuzom/usage.db` (not a test file) — a mistake I made, not a product defect.
Full incident report, current live-system state, and the exact repair SQL are in
**`08_TELEMETRY_AUDIT.md` → "AUDITOR INCIDENT"**. The live installation currently has an
empty, wrong-schema `claude_usage` table and needs authorized repair before further use.
This does not invalidate the findings below (all were reproduced against the isolated
worktree DB or established by direct source reading), but it is disclosed here because it
happened during economics-track testing and readers of this file need to know before trusting
any live `claude_usage`-derived number on this machine going forward.

---

## RED2-01 — Two non-reconciling Opus-baseline pricing tables both live at HEAD; the stale one feeds the "single source of truth"

- **Severity:** P0
- **Confidence:** PROVEN
- **Area:** Cost/savings computation — baseline counterfactual pricing
- **Title:** `router.py`'s live baseline-cost call site uses a STALE Opus price table ($15/$75 per Mtok) while the codebase's own "corrected" table ($5/$25 per Mtok) exists two files away — a self-documented 3x historical overstatement that was only partially fixed.

**Claim/invariant violated:** `retrospective.py::_derive_savings()` is explicitly documented
(`INV-COST-004`) as "the SINGLE source of truth for cost/savings." A single source of truth
requires exactly one pricing table feeding it. There are at least four.

**Observed:**
- `src/chuzom/cost.py:2190-2260` — `BASELINE_PRICING = {"haiku":(0.80,4.0), "sonnet":(3.0,15.0), "opus":(15.0,75.0)}`, comment tags it `v9.2.2`. Consumed by `_get_baseline_cost()`.
- `src/chuzom/cost.py:2650-2740` — a *second*, later-added pricing block: `LATEST_OPUS_MODEL = "claude-opus-4-8"`; `_OPUS_PRICING = {"claude-opus-4-8": (5.0, 25.0), ...}`, with an explicit in-code confession:
  > "History: the previous constants were $15/$75 labelled 'Opus 4.6' — wrong on two axes ... Every historical `saved_usd` was therefore ~3x inflated."
- `src/chuzom/router.py:2660-2720` (live call site, executed on every routed call) computes `_baseline_equivalent_cost_usd` via `cost._get_baseline_for_task()` + `cost._get_baseline_cost()` — **which reads the STALE `BASELINE_PRICING` table**, not `_OPUS_PRICING`. A near-identical second call site exists at `router.py:2975`.
- `src/chuzom/types.py:245-274` — a *third* table, `MODEL_COST_PER_1K = {"haiku":0.001,"sonnet":0.009,"opus":0.045}` (0.045/1K = $45/1K blended ≈ derived from the same stale $15/$75 pair). Imported by `tools/admin.py`, `commands/test.py`.
- `src/chuzom/benchmarks.py:25-84` — a *fourth* table, `_MODEL_COST_PER_1K` (`"anthropic/claude-opus-4-6": 0.045`, same stale derivation) plus a `_DEFAULT_COST = 0.005` fallback for unrecognized models.
- `src/chuzom/hooks/savings_logger.py` — a *fifth*, independently-maintained "CORRECTED" table `_PRICING_PER_MTOK` (`("claude","claude-opus-4-8"): (5.00, 25.00)`), used only by the direct-routing savings path, not by the router.py ledger path.

**Reproduction (PROVEN, executed against clean worktree via `.venv-audit/bin/python`, no production data touched):**
For a synthetic 100,000-input / 20,000-output "research"/"complex" call:
- `router.py`'s live execution-ledger path (`cost._get_baseline_cost` + stale `BASELINE_PRICING`) → **$3.00** baseline.
- The codebase's own "corrected" pricing (`cost._OPUS_PRICING["claude-opus-4-8"]`) for the identical tokens → **$1.00** baseline.
- **Exact 3.0x divergence**, reproduced numerically, not inferred.

**Why it matters:** `router.py`'s stale-priced `_baseline_equivalent_cost_usd` is written into
`execution_ledger.py`'s `baseline_equivalent_cost_usd` column (schema confirmed at
`execution_ledger.py:~202`, aggregated at `~452-513` via `get_period_accounting()`), which is
consumed **directly and exclusively** by `retrospective._derive_savings()`:
```python
def _derive_savings(start, end) -> float:
    try:
        acc = get_period_accounting(start.timestamp(), end.timestamp())
        return round(max(0.0, acc.baseline_equivalent_cost_usd - acc.actual_cost_usd), 6)
    except Exception:
        return 0.0
```
This function is the audit-confirmed single source of truth for the retrospective/debrief
savings figure. It is fed by the *stale* table, not the *corrected* one. The corrected $5/$25
table exists and is used elsewhere (`hooks/savings_logger.py`'s separate direct-answer path),
so the codebase clearly knows the old price is wrong — it just didn't finish threading the fix
through the primary ledger path that its own "single source of truth" depends on.

**Root cause:** the $15→$5 / $75→$25 pricing fix (visible, dated, self-described as a bug fix
in `cost.py`'s own comments) was applied to the newer `_OPUS_PRICING` block and to
`hooks/savings_logger.py`, but the older `BASELINE_PRICING` table — still wired into the live
`router.py` ledger-attempt call sites — was never removed or repointed at the new constants.
Classic incomplete-refactor / two-tables-for-one-concept defect.

**Why tests missed it:** nothing asserts `BASELINE_PRICING == _OPUS_PRICING`-derived values, or
that `router.py`'s baseline call sites use the same constant as `retrospective.py` expects. Each
table has isolated unit coverage (if any) for its own module; no cross-module reconciliation
test exists.

**Blast radius:** every `_derive_savings()`-based figure (retrospective/debrief "$ saved" line)
is inflated ~3x for any research/complex-routed session — the exact category this feature exists
to make credible. `router.py:2975`'s duplicate call site means the error is doubled across at
least two ledger-attempt code paths per session.

**Defect class elsewhere?** Yes — see RED2-03 (quota_savings.py's own $50/week calibration
comment still cites the stale $15/$75 pair to justify its constant) and RED2-05
(`get_routing_savings_vs_sonnet` self-documented misnomer). This is a systemic "N sources of
truth for one number" architecture, not an isolated bug.

**Recommended fix:** delete `BASELINE_PRICING`/`CLAUDE_RATES_PER_M` (cost.py), `MODEL_COST_PER_1K`
(types.py), and `_MODEL_COST_PER_1K`/`_DEFAULT_COST` (benchmarks.py); make `_OPUS_PRICING` /
`LATEST_OPUS_MODEL` the only pricing constant in the package, imported everywhere. Add a test
that fails the build if more than one Opus per-token price literal exists in `src/`.

**Regression test:** a synthetic-session test (see reproduction above) asserting
`retrospective._derive_savings()` output for a fixed token count matches a hand-computed value
using ONLY the corrected $5/$25 rate — would have failed at HEAD.

**Release blocking:** **Y**

---

## RED2-02 — `get_savings_summary()` cannot distinguish "genuinely zero savings" from "the query failed"

- **Severity:** P1
- **Confidence:** PROVEN (by source; live reproduction against a safe/isolated DB not
  completed — see incident note above)
- **Area:** Savings aggregation / fail-open telemetry
- **Title:** Query failure and zero-data both render as an identical, fully-populated
  "$0.00 saved" response — indistinguishable to any caller or the user.

**Observed**, `src/chuzom/cost.py:2116-2196`, `get_savings_summary(period)`:
- Docstring states outright: *"Returns zeroed-out values if no data exists or the query fails."*
- Both the exception path (query prep/execution raises) and the `not row or row[0] == 0` path
  return the **identical** shape: `{"total_calls": 0, "total_tokens": 0, "cost_saved_usd": 0.0,
  "time_saved_sec": 0.0, "by_model": {}}`.
- Confirmed live callers: `src/chuzom/tools/routing.py:205`, `src/chuzom/tools/admin.py:164`.

**Why it matters:** a DB-permission error, a locked file, a missing table (pre-migration DB), or
a genuinely idle period are all indistinguishable to the caller. Any surface built on this
function cannot tell "chuzom saved you nothing today" from "chuzom's telemetry is broken today"
— and per the mandate's fail-open framing, a broken telemetry path silently *looks* like a
quiet, well-behaved zero rather than an error state that should be surfaced.

**Exact reproduction (source-level, PROVEN):** read the function body directly —
`cost.py:2116-2196`. The `try/except Exception:` wrapping the query, and the separate
`if not row or row[0] == 0:` branch immediately below it, both `return` the literal same dict
constructed from a local `_EMPTY = {...}`-equivalent inline literal. No error is logged, raised,
or attached to the return value at either site.

**Live numeric reproduction — INCOMPLETE / VOID:** I attempted to reproduce this end-to-end by
forcing a query failure against a database. I set `CHUZOM_HOME` to an isolated `mktemp -d`
directory, wrongly assuming `chuzom.cost._get_db()` honors it. It does not (see RED2-07below) —
the script actually opened and mutated the user's real `~/.chuzom/usage.db`. The single
completed run (before I stopped) DID reproduce the ambiguity — `get_savings_summary()` returned
the identical `{'total_calls': 0, ...}` zero-shape immediately after I dropped/recreated
`claude_usage` with an incompatible schema — but because that came at the cost of real data loss,
I am not treating it as a clean PROVEN reproduction and it must be redone against a disposable
DB file (e.g., `sqlite3.connect(":memory:")` or an explicit path argument, never an env var
assumed-but-unverified to redirect storage) before this finding can be upgraded past
"PROVEN by source, reproduction pending in a safe environment."

**Root cause:** fail-open-by-default exception handling with no distinct sentinel/error field
in the return contract.

**Why tests missed it:** any test that seeds real zero-usage data would pass identically whether
or not the exception path was hit — the two code paths are behaviorally fused by design.

**Blast radius:** `tools/routing.py` and `tools/admin.py` both surface this dict directly to
CLI/tool output; a user seeing "$0.00 saved this week" cannot know if that's true or if
telemetry silently broke.

**Defect class elsewhere?** Yes — the same `except Exception: return 0.0` fail-open pattern
recurs in `get_realized_savings()`'s per-table `_query_table()` helper (`cost.py:1893-1985`,
comment: *"Table may not exist on older DBs — treat as zero"*) and in
`retrospective._derive_savings()` itself (RED2-01).

**Recommended fix:** return a tri-state (`ok: bool`, or a distinct `error: str | None` field)
instead of collapsing "no data" and "query failed" into one shape. At minimum, log the exception
at `warning` level so it's visible in diagnostics even if the UI stays quiet.

**Regression test:** point `get_savings_summary()` at a DB file with `claude_usage` deliberately
missing/malformed (in an isolated temp file) and assert the return value is distinguishable from
a genuine-zero query against a well-formed, empty table.

**Release blocking:** N (P1, not P0 — no false-positive savings is produced, only an
undetectable false-zero/silent-failure ambiguity)

---

## RED2-03 — Quota-savings "percentage points" figure rests on a hardcoded, admittedly-estimated $50/week constant that itself cites the stale (3x-wrong) Opus price

- **Severity:** P1
- **Confidence:** STRONG EVIDENCE
- **Area:** Subscription-quota-savings conversion (`quota_savings.py`)
- **Title:** The user-facing "saved Xpp wk / Ypp 5h" figure converts dollars to subscription
  percentage points using a constant the code itself labels an estimate — and that estimate's
  own justification comment still uses the discredited $15/$75 pricing from RED2-01.

**Observed**, `src/chuzom/quota_savings.py`:
- Module docstring: *"``saved_usd`` is denominated in dollars ... we need a `$_per_pp` ratio.
  This module uses a **configured constant** by default (`CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV`,
  default $50 ...). The constant is intentionally documented as an estimate."*
- `_DEFAULT_WEEKLY_QUOTA_USD = 50.0`, justified in a comment: *"Anthropic Claude Pro Max ≈
  $200/month subscription; rough Opus-cost equivalent at **$15-in/$75-out** per million tokens
  lands the weekly budget in the $40-60 range."* — this is the exact stale rate RED2-01 proves
  is ~3x too high elsewhere in the same codebase. The $50 anchor was never revisited after the
  $5/$25 pricing fix landed.
- `compute_quota_savings()` (`quota_savings.py:183+`) calls `_calibration_usd_per_pp()`
  (`:130`) to get `(usd_per_pp, source)`; `source` is one of `"configured"` (the estimate) or
  `"observed"` — the docstring for the module marks the observed/measured calibration path as
  **not yet implemented** ("follow-up (T-QS-2)"), meaning `"configured"` is the *only* source
  that currently exists in v1.1.1.
- Surfaced to the user via the routing-notice line (`hooks/response_formatter`) as
  `"saved Xpp wk / Ypp 5h"` and via the `llm_quota_saved` MCP tool.

**Why it matters:** a user-visible number ("you saved N percentage points of your weekly quota")
is presented without qualification, but is derived from (a) a `saved_usd` figure that RED2-01
shows can be ~3x inflated on the live ledger path, multiplied by (b) a hand-picked $50/week
conversion constant that is itself justified using the same stale pricing. Two independent
sources of inflation compound in the same displayed metric. There is no `is_estimated` flag
surfaced alongside the pp figure in the short-form display (`short_form()`only formats the
number; `calibration_source` exists on the dataclass but I did not find it consumed by the
routing-notice string — see "not tested" below).

**Confidence rationale (why STRONG EVIDENCE, not PROVEN):** I did not execute
`compute_quota_savings()` end-to-end with real token/session data (this would have required
querying `claude_usage`, and I have withdrawn from further live-DB testing per the incident in
`08_TELEMETRY_AUDIT.md`). This finding is proven at the source-and-constant level; the runtime
magnitude of the compounded error was not independently measured.

**Root cause:** a hardcoded calibration constant whose derivation depends on a pricing table
that was later found wrong, with no update mechanism or staleness check tying the two together.

**Why tests missed it:** no test asserts `_DEFAULT_WEEKLY_QUOTA_USD`'s derivation is consistent
with the current `_OPUS_PRICING` table; the two live in unrelated modules.

**Blast radius:** every session that shows the "saved Xpp wk" routing-notice suffix.

**Defect class elsewhere?** Yes — same "stale-derived-constant persists after a pricing fix"
pattern as RED2-01.

**Recommended fix:** derive `_DEFAULT_WEEKLY_QUOTA_USD` programmatically from `_OPUS_PRICING`
(single source), or clearly mark the pp figure as an estimate in the displayed string itself,
not just in code comments.

**Regression test:** assert `_DEFAULT_WEEKLY_QUOTA_USD`'s comment-stated derivation, recomputed
from `cost._OPUS_PRICING[cost.LATEST_OPUS_MODEL]`, falls within the stated $40-60 band; currently
it does not (recomputing with $5/$25 instead of $15/$75 yields a materially lower dollar figure).

**Release blocking:** N (P1 — compounding-estimate problem, not a fabricated number, and clearly
commented as an estimate in source even if not in the UI string)

---

## RED2-04 — Five different "savings" fields in `session_spend.py`; only one is honestly gated on subscription-vs-metered, and three have self-documented historical bugs claimed-but-not-independently-reverified as fixed

- **Severity:** P1
- **Confidence:** STRONG EVIDENCE (claims-fixed-not-independently-reverified)
- **Area:** Session-level spend/savings accounting
- **Title:** `get_summary()` returns `net_savings_usd`, `baseline_avoided_usd`,
  `potential_savings_usd`, `realized_savings_usd`, and `real_dollars_avoided_usd` side by side;
  only `real_dollars_avoided_usd` is gated by `_host_is_metered()`. The other four —
  including the one named "realized," which reads as the most authoritative — are the same
  Opus-baseline-avoided figure regardless of whether the host is a flat-rate subscription.

**Observed**, `src/chuzom/session_spend.py:318-440`:
```python
@property
def net_savings_usd(self) -> float:
    """... this over-states real dollars. Use `real_dollars_avoided_usd` for the
    honest cash figure ..."""
    return max(0.0, self.opus_equivalent_usd - self.total_usd)

@property
def real_dollars_avoided_usd(self) -> float:
    """Dollars the user would ACTUALLY have paid absent routing. ~$0 on a
    flat-rate subscription ..."""
    metered = _host_is_metered()   # only this property checks metered status
    return self.net_savings_usd if metered else 0.0

@property
def potential_savings_usd(self) -> float:
    return self.net_savings_usd    # NOT gated on metered

@property
def realized_savings_usd(self) -> float:
    """Savings actually preserved ..."""
    kept = max(0, self.call_count - self.overridden_turns)
    return round(self.potential_savings_usd * kept / self.call_count, 6)  # NOT gated
```
`get_summary()` returns all five fields in one dict with no field marking which are
subscription-adjusted. `tools/admin.py:980-981` reads `potential_savings_usd` and
`realized_savings_usd` — both display as "Potential saved" / "Realized saved" — **neither is
the metered-aware honest figure**; `admin.py:632-633` separately reads `baseline_avoided_usd`
and `real_dollars_avoided_usd` in a different table ("AVOIDED vs OPUS BASELINE" / "Real $"
columns) — that second table IS correctly split. So the same session's numbers appear twice in
the admin CLI output under different section headers, one section honestly split by
metered-status and one (the "Potential saved" / "Realized saved" block) not split at all.

**Session context confirming this is not hypothetical:** this very audit session's own
SessionStart banner reads `⚡ chuzom ACTIVE — subscription mode`, i.e., non-metered — the exact
condition under which `net_savings_usd`/`potential_savings_usd`/`realized_savings_usd` diverge
from `real_dollars_avoided_usd` (which would legitimately show ~$0).

**Self-documented historical bugs found in the same file/hooks (claimed fixed at HEAD, not
independently re-verified end-to-end by me):**
1. `hooks/auto-route.py:3611` — prior to a route-id-minting fix, `realized_savings_usd`
   "stayed 0 in production" because two independently-minted route IDs never matched in the
   ledger join.
2. `hooks/stop-enforce.py:188` (INV-ENF-002/003) — prior to `_record_override` parity between
   the plain-text-override path and the tool-call-override path, `realized_savings_usd` was
   "systematically overcounted."
3. `hooks/enforce-route.py:891` — in "advise" mode, `realized_savings_usd` showed 0 even when
   routing was honored every turn, until adoption-recording was duplicated into the advise
   early-exit branch.

All three comments describe the bug AND claim a specific fix is in place at HEAD. I read the
described fixes in context (shared `_directive_id` minting in auto-route.py; `_record_override`
called from `stop-enforce.py::main()`; the advise-mode duplicated recording block in
enforce-route.py) and they are present in the source. I did **not** run an end-to-end session
(route → override/adopt → Stop hook → ledger aggregation → `get_summary()`) to independently
confirm the fixes actually close the gaps as described — this requires the full hook pipeline
running in a real Claude Code session, which is outside what I could safely reproduce given the
production-DB incident and time remaining.

**Why it matters:** this is exactly the class of bug the mandate calls "materially false savings"
— a metric that reads 0 or overcounts by design under specific, ordinary conditions (advise mode;
overridden turns; ID-mismatch races). The fixes are plausible and specific, not hand-waved, which
is why I am not calling this PROVEN-broken at HEAD — but three independent historical instances of
the *same class* of bug (realization accounting silently wrong) in one small area is a strong
signal the join is fragile and worth a dedicated end-to-end regression test, which does not appear
to exist (no test file located that drives the full hook chain and asserts final
`realized_savings_usd` against a hand-computed value).

**Recommended fix:** add exactly the end-to-end regression test described above. Separately,
rename/restructure the `get_summary()` dict so subscription-aware fields are unambiguous by name
(e.g., prefix non-metered-adjusted fields as `*_baseline_only`) rather than relying on the caller
to know which of five similarly-named fields is "honest."

**Release blocking:** N as currently understood (fixes are present and specific) — but flag for
a required end-to-end test before the next release if one doesn't already exist; if RED-1/RED-3
independently exercised the live hook chain, their findings should be cross-checked against this.

---

## RED2-05 — `get_routing_savings_vs_sonnet()`: self-admitted misnomer, a fourth baseline-labeling inconsistency

- **Severity:** P2
- **Confidence:** PROVEN (by source)
- **Area:** Naming / API surface honesty
- **Title:** A function named "vs Sonnet" has never compared against Sonnet; its own docstring
  says so.

**Observed**, `src/chuzom/cost.py:2997-3013`:
```python
async def get_routing_savings_vs_sonnet(days: int = 0) -> dict:
    """Compute savings by comparing actual cost vs the latest-Opus host baseline.
    ...
    NOTE: the ``_vs_sonnet`` name is historical and misleading — the baseline is
    the latest Opus (``LATEST_OPUS_MODEL``), never Sonnet. Rename is deferred to
    avoid breaking callers; see RETROSPECTIVE B-8.
    """
```

**Why it matters:** low severity in isolation (an internal function name), but it is the fourth
distinct "which baseline model" naming/labeling inconsistency found in this audit (alongside
`BASELINE_PRICING` vs `_OPUS_PRICING` in RED2-01, and the `_get_baseline_for_task()` logic that
varies by task_type/complexity vs. the "2026-07-12 user decision" to standardize on
always-Opus-equivalent elsewhere, referenced in `hooks/savings_logger.py`). A codebase this
inconsistent about which baseline it's even claiming to compare against makes independent
verification by a user or downstream engineer materially harder — every "savings" number requires
first discovering which of several inconsistently-named baselines actually produced it.

**Recommended fix:** rename to `get_routing_savings_vs_opus_baseline()` per the function's own
deferred-rename note; audit all callers for the same "vs Sonnet" naming.

**Release blocking:** N

---

## RED2-06 — `ledger_coverage_rate`: a self-acknowledged wrong-on-a-fresh-ledger proxy metric, currently unconsumed

- **Severity:** P3
- **Confidence:** STRONG EVIDENCE
- **Area:** `routing_quality.py` — v2 route-ledger coverage reporting
- **Title:** `summarize()`'s `ledger_coverage_rate` is documented in-source as wrong in the
  common case (100% on a fresh ledger with zero real routes), and — per exhaustive grep across
  `src/` — has no current consumer anywhere in v1.1.1.

**Observed**, `src/chuzom/routing_quality.py`:
```python
# Proxy: v2 / (v2 + legacy). WRONG on a fresh ledger (100% on 0 real routes);
# true coverage needs an external count of total route attempts. Documented gap.
"ledger_coverage_rate": len(v2) / max(1, len(v2) + len(legacy)),
```
`grep -rn "ledger_coverage_rate\|routing_quality.summarize" src/` (excluding the definition
site itself) returns no matches — this metric is currently write-only telemetry, not displayed
anywhere in v1.1.1.

**Why it matters (low, but real):** exactly the kind of "metric that looks excellent when
observation coverage is poor" the mandate asks me to hunt for — a brand-new install would show
100% ledger coverage with zero actual routing activity. It is currently harmless only because
nothing reads it yet; if a future release wires this into a dashboard without fixing the
denominator, it becomes a real user-facing false-confidence signal.

**Recommended fix:** either fix the denominator (track total route attempts independently of
the v2/legacy split) before ever surfacing it, or leave it internal but comment it as
`INTERNAL-ONLY, do not surface without fixing denominator` to prevent accidental future exposure.

**Release blocking:** N

---

## Summary table

| ID | Severity | Confidence | Title |
|---|---|---|---|
| RED2-01 | P0 | PROVEN | Stale $15/$75 Opus baseline still feeds the "single source of truth" ledger path; 3.0x reproduced divergence vs. the codebase's own corrected $5/$25 table |
| RED2-02 | P1 | PROVEN (source); live repro incomplete | `get_savings_summary()` can't distinguish real zero from query failure |
| RED2-03 | P1 | STRONG EVIDENCE | Quota "percentage points" figure rests on a hardcoded $50/week constant justified via the same stale pricing RED2-01 disproves |
| RED2-04 | P1 | STRONG EVIDENCE | Five session-level "savings" fields, only one honestly gated on subscription-vs-metered; three sibling bugs claimed-fixed, not independently re-verified end-to-end |
| RED2-05 | P2 | PROVEN | `get_routing_savings_vs_sonnet()` — self-admitted misnomer, 4th baseline-labeling inconsistency |
| RED2-06 | P3 | STRONG EVIDENCE | `ledger_coverage_rate` proxy metric wrong-by-design on fresh ledgers; currently unconsumed |

See `08_TELEMETRY_AUDIT.md` for the fail-open/telemetry-integrity track and the mandatory
auditor-incident disclosure.
