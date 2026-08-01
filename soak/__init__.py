"""Phase 0 realized-savings corpus soak package.

Measures "does a defensible realized-savings number exist" by replaying a
small, committed, pre-redacted corpus of representative prompts through the
real router dispatch path and aggregating the resulting execution-ledger rows
via ``chuzom.execution_ledger.get_session_accounting``.

Scope (Phase 0, approved — see phase0_brief.md):
  * Soak-only measurement. Production hook<->router route_id reconciliation
    is deferred to Phase 0.5.
  * ``baseline_tokens`` is a conservative ``actual_proxy``, not precise
    frontier tokenization.
  * ``agent_marked`` adoption is exercised only inside the soak harness; the
    production transport for it is Phase 1.

Modules:
  * ``corpus_schema`` -- row schema, validation, and the secret_scrubber-backed
    privacy check for the committed ``corpus/v1.jsonl``.
  * ``replay`` -- drives ``route_and_call`` over the corpus and reads back
    session-scoped accounting.
  * ``report`` -- aggregates replay results into ``soak/report.json``.
  * ``ci`` -- bootstrap confidence intervals used by ``report``.
"""

from __future__ import annotations

CORPUS_VERSION = "v1"
