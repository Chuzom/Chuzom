# Public Chuzom v0.3.0 — Option B Roadmap

**Strategy: Complete Plugin Architecture → Benchmark → Release as Beta**

This document outlines the revised roadmap: finish the plugin seam (C-1/C-2/C-3), validate with RouterArena, then release `v0.3.0-beta` with performance benchmarks.

## Pre-Release: Plugin Architecture & Validation

### C-1: Redaction Plugin Seam (✅ MERGED)
- Inverted `redaction_routing.py` to use registry
- All redaction tests pass

### C-2: Audit Plugin Seam (🔄 PR #94, awaiting merge)
- Inverted `audit_routing.py` to use registry
- Lazy AuditLog initialization for test compatibility
- All audit tests pass

### C-3: Quota Plugin Seam (📋 PLANNED)
**Scope:** Abstract quota backend so router logic is agnostic to storage (SQLite vs Postgres).

**Deliverables:**
- [ ] `QuotaBackend` Protocol in `src/chuzom/plugins/quotas.py`
- [ ] Registry/factory pattern for backend selection
- [ ] Refactor existing SQLite quota logic into `SQLiteQuotaBackend`
- [ ] Refactor private Postgres backend to implement `QuotaBackend`
- [ ] Integration into `route_and_call()` quota check
- [ ] Tests for the protocol + both backends

**Effort:** 3-5 days (similar scope to C-1/C-2)  
**Merge criteria:** All quota tests pass, no enterprise code leaked into public

### RouterArena Benchmark (📋 PLANNED)
**Goal:** Validate chuzom's cost-saving claim with objective data vs alternatives.

**Deliverables:**
- [ ] `scripts/run_router_benchmark.py` — runs chuzom through benchmark dataset
- [ ] Baseline comparisons (vs always-expensive, always-cheap)
- [ ] Key metrics:
  - **Pareto frontier chart** (cost vs quality) — PRIMARY
  - **Cost savings %** — headline claim (e.g., "70% cost reduction")
  - **Routing accuracy** — % of correct model choices
  - **Latency overhead** — p95/p99 (target: <50ms)
- [ ] `docs/benchmarks.md` — detailed methodology + results
- [ ] README update with benchmark summary + embedded graph

**Effort:** 4-6 days initial + 2-3 iterations (tune routing, re-run, analyze)  
**Success criteria:** Results show chuzom in top-left quadrant (high quality, low cost)

### Release: v0.3.0-beta
**Why beta?** Signals feature-complete & validated, but API unstable + ongoing hardening.

- [ ] Tag `v0.3.0-beta` on GitHub
- [ ] Publish to PyPI
- [ ] Announce with benchmark results as primary marketing asset
- [ ] Gather early adopter feedback

---

## Post-Beta: Hardening Phases (v0.3.0 stable)

Once beta is live and you're collecting user feedback, run hardening phases in parallel.

## Phase 1: Isolation & Cleanup (1-2 PRs)

**Goal:** Separate public and enterprise code/tests/docs completely.

- [ ] Enterprise tests moved to `tests/enterprise/` (✓ DONE)
- [ ] `pytest.ini` configured to exclude `tests/enterprise` from default runs (✓ DONE)
- [ ] `docs-private/` folder structure created with enterprise docs (✓ DONE)
- [ ] `.gitignore` updated to keep `docs-private/` local-only (✓ DONE)
- [ ] Build config verified: `src/chuzom/enterprise` excluded from wheel/sdist (✓ DONE)
- [ ] README.md updated with "Running Tests" section explaining the split
- [ ] Verify public test suite runs cleanly: `pytest tests/ -v`

**Owner:** Yali  
**Timeline:** This sprint  
**Merge criteria:** All checks green, public tests pass

---

## Phase 2: Core Hardening (2-3 PRs)

**Goal:** Harden the public routing core (security, performance, docs).

### PR 2a: Security Audit & Fixes
- [ ] Security review of routing input validation
- [ ] Audit prompt/model/provider parameter handling
- [ ] Add input sanitization if needed
- [ ] Review quota enforcement correctness
- [ ] Add security tests for edge cases

### PR 2b: API Documentation & Docstrings
- [ ] Add comprehensive docstrings to:
  - `route_and_call()` with examples
  - Quota tracking functions
  - Redaction functions
  - CLI commands
- [ ] Add type hints to all public functions
- [ ] Add `docs/API.md` with reference guide

### PR 2c: Performance & Observability
- [ ] Establish routing latency baseline (measure, report)
- [ ] Add performance tests (mock providers, latency assertions)
- [ ] Improve logging for debugging routing decisions
- [ ] Document expected performance characteristics

**Owner:** Yali + volunteers  
**Timeline:** Weeks 1-2  
**Merge criteria:** Security audit passed, 90% public code documented

---

## Phase 3: Documentation (1-2 PRs)

**Goal:** Create comprehensive public documentation.

- [ ] **docs/README.md** — Getting started (5 min to first successful route)
- [ ] **docs/QUICKSTART.md** — Copy-paste examples for Claude Code, Cursor, Gemini CLI
- [ ] **docs/QUOTA_TRACKING.md** — Developer guide to budget tracking
- [ ] **docs/REDACTION.md** — PII redaction capabilities + configuration
- [ ] **docs/TROUBLESHOOTING.md** — Common issues + solutions
- [ ] **docs/ARCHITECTURE.md** — High-level design (public features only)
- [ ] **examples/** folder — Runnable integration examples

**Owner:** Yali (technical content)  
**Timeline:** Week 2-3  
**Merge criteria:** All docs rendered cleanly, examples tested

---

## Phase 4: Testing & CI (1 PR)

**Goal:** Comprehensive test coverage and public-specific CI.

- [ ] E2E tests for critical journeys:
  - Basic routing with mock provider
  - Quota tracking (reserve, consume, release)
  - Redaction (verify PII scrubbed)
  - Error handling (invalid provider, timeout)
- [ ] Benchmark vs alternatives (vs RouteLLM, LiteLLM):
  - Latency comparison
  - Memory footprint
  - Startup time
- [ ] CI job: `public-install-verify`
  - Build wheel, install in clean env
  - Run smoke tests
  - Verify enterprise NOT importable
- [ ] Coverage report (target: 85%+ for public code)

**Owner:** Yali + QA  
**Timeline:** Week 3-4  
**Merge criteria:** 85%+ coverage, E2E tests green, benchmark report published

---

## Phase 5: Security & API Polish (1-2 PRs)

**Goal:** Ensure public API is production-ready (docs, types, security).

- [ ] Security audit of routing core (input validation, edge cases)
- [ ] Full docstrings on all public functions
- [ ] Full type hints on all public APIs
- [ ] Remove any lingering enterprise dependencies
- [ ] Phase 2-3 tests added for critical paths

**Owner:** Yali  
**Timeline:** Week 3-4 (in parallel with beta usage feedback)  
**Merge criteria:** Security audit complete, 90%+ API documented

---

## Enterprise Backlog (Hidden, Post-Beta)

Keep private in `docs-private/` + private `chuzom-enterprise` repo:
- SCIM/OIDC multi-tenant provisioning
- RBAC + admin dashboard  
- Hash-chained audit logging
- Postgres multi-instance quota coordination
- Advanced analytics + usage insights

This backlog remains **hidden from public GitHub** until enterprise license model is finalized.

---

## Timeline Summary (Option B)

### Pre-Release (1-2 weeks)
- **This week:** C-2 merge, C-3 implementation begins
- **Week 1:** C-3 complete, RouterArena setup begins
- **Week 1-2:** RouterArena benchmark runs + iterations
- **End of Week 2:** **v0.3.0-beta released to PyPI**

### Post-Beta (Parallel with Usage Feedback)
- **Week 2-3:** Phase 5 hardening (security, docs, types)
- **Week 3-4:** Collect early adopter feedback, iterate on API
- **Week 4-5:** **v0.3.0 stable released**

---

## Success Criteria

| Milestone | Definition of Done |
|-----------|-------------------|
| **C-3** | Quota plugin seam complete, all quota tests pass |
| **RouterArena** | Pareto frontier shows cost savings claim validated |
| **v0.3.0-beta** | Live on PyPI, benchmark results in README |
| **v0.3.0 stable** | Full API documented, security audit passed |

---

## Release Marketing Hook

**v0.3.0-beta headline:** "35–70% cost reduction on LLM workloads. Routed to the cheapest model that can do the job. Benchmarked against Claude Opus."

With RouterArena data, you have an objective foundation for this claim—not just marketing rhetoric.
