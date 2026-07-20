"""Savings-integrity experiments (RETROSPECTIVE Deliverable 4).

A deterministic, offline harness that makes chuzom's savings claims falsifiable
end-to-end. It replays recorded multi-turn *session traces* (three realistic
shapes) through the REAL production savings code — cost.get_savings_by_period,
SessionSpend, the host-metered switch — against a throwaway usage.db, then
checks:

  E-3  reconciliation  : each surface self-consistent; baseline_avoided == saved.
  E-4  counterfactual  : baseline_avoided vs real dollars under subscription /
                         metered / over-cap quota states (quantifies M-2 / M-3).
  E-5  properties       : window nesting, monotonicity, deterministic replay.
  E-7  report           : one scorecard per session shape -> report.md.

No network, no API keys, $0. The "recorded provider" cassette is the per-turn
token/cost recorded in bench/corpus/sessions/*.jsonl.
"""
