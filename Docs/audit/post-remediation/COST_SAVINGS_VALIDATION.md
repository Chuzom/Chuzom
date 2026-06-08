# Cost-Savings Validation

**Question being answered.** Can chuzom prove it saved the organisation money — net of hidden costs, reconciled against provider invoices?

**Verdict:** **Plausible but unverified.** Direct routing-cost instrumentation is real and usable; counterfactual ("would have spent"), reconciliation (against provider invoices), and net-of-hidden-cost reporting do not exist.

---

## 1. What chuzom currently measures

### 1.1 Per-call routing decisions

- `src/chuzom/cost.py` — `log_usage(...)` writes per-call rows into `~/.chuzom/usage.db` (table `usage`). Columns include `task_type`, `complexity`, `selected_model`, `final_provider`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`.
- `src/chuzom/lineage/` — additional structured lineage rows (post v0.2.x rewrite); `lineage` SQLite table with 22 columns including agent identity and inversion verdict.
- `src/chuzom/tools/dashboard.py:162,205` — local dashboard renders `actual_cost` vs. `baseline_cost`. The baseline here is **per-call counterfactual**: cost-if-routed-to-the-host-model. Not org baseline. Not direct-provider baseline.

### 1.2 What "baseline" means in code

The `baseline_cost` field is computed by `_estimate_opus_cost(...)` (helper in `router.py` / `cost.py`) — it estimates what the same call would have cost on Opus / Sonnet (whichever is configured as the "host" / "baseline" model in the user's profile). This is a **per-call** counterfactual, not a fleet-level baseline.

### 1.3 What chuzom does NOT measure

| Required for net-savings claim | State |
|---|---|
| Cost under direct-provider usage (no routing) | Not modelled. |
| Cost under organisation's previous default model | Not configured per org. |
| Cost including retries and fallbacks | Per-call cost row records final outcome; retry chain cost across providers is not aggregated under a single "turn cost" identifier in the visible schemas. |
| Cost including cached tokens | Provider prompt-cache cost reductions are not modelled (would require provider-side cache hit telemetry). |
| Cost including reasoning tokens | Reasoning-token cost is whatever LiteLLM reports; no separate accounting. |
| Cost including tool calls | Tool-call tokens are part of the model call cost; not separated. |
| Cost including failed requests | Not always captured. |
| Cost including shadow / evaluation traffic | No shadow-traffic mode in `router.py`. |

---

## 2. Pricing-data quality

| Property | State | Evidence |
|---|---|---|
| Accurate per model | Plausible | Per-model rates baked in `_COST_PER_1K` (text.py) and helpers; not all providers covered. |
| Versioned | ❌ | No timestamped pricing entries; no `priced_at` column. |
| Reconciled against provider invoices | ❌ | `grep -rn "invoice\|reconcile_provider" src/chuzom/` returns no application-code match. |
| Region-specific | ❌ | No region axis. |
| Historically reproducible | ⚠️ | Logged `cost_usd` is the as-priced-at-call-time number; if rates change, old rows are NOT re-priced. |

**Implication.** Without a pricing-version pipeline and an invoice-reconciliation job, a Finance auditor cannot confirm that the chuzom-reported "we saved $X" matches the provider invoice for the same period within a defined tolerance.

---

## 3. Savings analysis — what the system can / cannot report today

| Report | Achievable today | Notes |
|---|---|---|
| Gross model-cost reduction | ⚠️ Per-call delta exists; **fleet aggregate is per-user-per-host** (no central rollup). |
| Net cost reduction | ❌ Net-of-rework / net-of-retries / net-of-bypass not modelled. |
| Savings by user | ⚠️ Lineage carries `user_id` (post Tier 1); per-user SQL queries possible against `~/.chuzom/usage.db`, but each host has its own DB. |
| Savings by team | ❌ No `team_id`. |
| Savings by project | ❌ No `project_id`. |
| Savings by tool | ⚠️ `task_type` is the proxy; not the same as IDE / CLI tool. |
| Savings by repo | ❌ Not modelled. |
| Savings by provider / model | ✅ Per-call rows include both. |
| Savings by routing rule | ⚠️ `classifier_method` is logged; not joined to a rule registry. |
| Savings by time period | ✅ Per-call timestamps. |
| Savings after retries | ❌ Retry / fallback aggregation across one turn not surfaced. |
| Savings after failed requests | ❌ Failure costs not consistently included. |
| Estimated vs. verified | ❌ All numbers are estimates from chuzom-side metering. |

---

## 4. Hidden-cost coverage

The net-value model in the audit charter:

```
Net value = Direct provider cost saved
         − Additional model-call cost (cheap model needed extra calls)
         − Additional infrastructure cost (chuzom hosting, dashboards, audit DB)
         − Chuzom operating cost
         − Additional developer time (waiting for routed model, retry frustration)
         − Additional failure / rework cost
         − Quality degradation cost (more agent steps, more human correction)
```

**Coverage by chuzom today:**

| Term | Measurable today? |
|---|---|
| Direct provider cost saved | Approximate (counterfactual is per-call, not fleet) |
| Additional model-call cost | Yes, per-call rows exist |
| Additional infrastructure cost | ❌ Outside scope of chuzom telemetry |
| Chuzom operating cost | ❌ Same |
| Additional developer time | ❌ Not measured; would require IDE-side TTFT capture + comparison with direct-provider baseline |
| Additional failure / rework cost | ❌ Not modelled |
| Quality degradation cost | ❌ Not modelled; requires a quality corpus |

**Of the seven terms, two are measurable today.** A net-savings number from chuzom alone is therefore **directional, not authoritative**. Finance cannot rely on it without an external reconciliation pipeline.

---

## 5. Central financial reporting — can Finance answer these?

| Finance question | Achievable today? |
|---|---|
| What did we spend this month? | ⚠️ Yes per-host, no across the fleet. |
| What would we have spent without chuzom? | ⚠️ Per-call counterfactual against host model only. |
| How much was actually saved? | ❌ Gross only; net unmeasured. |
| Which teams saved? | ❌ No team axis. |
| Which strategies created value? | ⚠️ `classifier_method` correlates; not joined to outcomes. |
| Which routes reduced cost but damaged performance? | ❌ No performance / quality data. |
| Which providers are most cost-effective? | ⚠️ Per-provider tier-cost reports exist. |
| Outliers (users, agents)? | ⚠️ Lineage queries possible; not surfaced in a dashboard. |
| Close to budget? | ⚠️ Global only. |
| Reconcile with provider invoices? | ❌ No reconciliation pipeline. |

---

## 6. Required experiments before claiming net savings

These experiments are necessary to move the cost-savings verdict from "Plausible but unverified" to "Directionally supported" or higher:

1. **Direct-provider baseline period.** A fixed two-week window where a subset of pilot developers route directly to provider (no chuzom). Capture per-developer cost + completion + TTFT.
2. **Routed period** of the same developers and same task corpus. Capture the same metrics.
3. **Controlled corpus**: 50 fixed tasks per developer, prompts + expected outputs predefined. Score outputs blind against a rubric.
4. **Provider invoice reconciliation.** Pull the provider invoice for the routed period. Compare gross cost against logged cost. Define tolerance (suggested ≤ 2% in aggregate, ≤ 10% per developer).
5. **Net-savings calculation.** Direct − Routed − ChuzomOps − any QualityRegressionCost (estimated from corpus delta).
6. **Significance.** Sample size large enough to give a confidence interval on the savings number (e.g. 95% CI not crossing zero).

**Until those run, "chuzom saves X%" is a marketing claim, not an evidence-backed financial statement.**

---

## 7. Confidence

| Item | Confidence |
|---|---|
| Gross routing-cost instrumentation exists | High |
| Per-call counterfactual against host model exists | High |
| Net-savings claim against direct-provider baseline | **Not made; unproven** |
| Reconciliation against provider invoice | **Not made; pipeline absent** |
| Hidden-cost coverage of the 7-term net-value model | **2 / 7** |

---

## 8. Verdict

**Cost-saving verdict (using the audit's four-level scale):**

| Level | Definition | Match? |
|---|---|---|
| Verified | Reconciled against provider invoice, controlled comparison, statistical bound | ❌ |
| Directionally supported | Per-call counterfactual + lineage; gross trend observable | ⚠️ Half-met |
| Plausible but unverified | Code paths exist to measure; no controlled comparison | ✅ |
| Misleading | Specific claims contradicted by code | n/a |
| Unsupported | No measurement at all | n/a |

**Final classification: Plausible but unverified.** Reclassify after the experiments in §6 run.
