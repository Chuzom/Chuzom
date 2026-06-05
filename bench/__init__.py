"""Tessera benchmark harness — head-to-head router comparison on a fixed corpus.

Design rule: every comparison decision is data-derived. No human judgment in
the aggregate ranking. The harness produces a per-router scorecard and a
Pareto frontier (cost vs quality) so the cheapest router that preserves
quality wins by definition.
"""
