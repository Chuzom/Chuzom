# Public Chuzom v0.3.0 — Hardening Phases

This document outlines the 5-phase hardening roadmap to take Chuzom from "feature-complete but rough" to "production-ready for developers."

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

## Phase 5: Release (1 PR + release management)

**Goal:** Tag v0.3.0-public, publish to PyPI, launch.

- [ ] CHANGELOG.md updated with v0.3.0-public release notes
- [ ] Tag v0.3.0-public on GitHub
- [ ] Publish to PyPI: `python -m build && twine upload dist/*`
- [ ] Verify installable: `pip install chuzom-router==0.3.0`
- [ ] Smoke test public package
- [ ] Announce on social channels (if desired)
- [ ] Monitor for issues + performance reports in first week
- [ ] Keep public GitHub issues enabled for feedback

**Owner:** Yali (release lead)  
**Timeline:** Week 4-5  
**Merge criteria:** All prior phases complete, smoke tests pass

---

## Post-Release: Monitoring & Enterprise Backlog

### Public Monitoring
- Watch GitHub issues for bug reports
- Monitor PyPI download stats
- Collect user feedback on API usability
- Fast-track critical security fixes

### Enterprise Backlog
Keep private in `docs-private/` + private `chuzom-enterprise` repo:
- SCIM/OIDC multi-tenant provisioning
- RBAC + admin dashboard
- Hash-chained audit logging
- Postgres multi-instance quota coordination
- Advanced analytics + usage insights

This backlog remains **hidden from public GitHub** until enterprise license model is finalized.

---

## Success Criteria

| Phase | Definition of Done |
|-------|-------------------|
| 1 | Public + enterprise cleanly separated, tests isolated |
| 2 | Core routing hardened, 90%+ documented, security audit passed |
| 3 | Comprehensive public docs, examples runnable |
| 4 | 85%+ test coverage, benchmarks published, CI gates enforced |
| 5 | v0.3.0-public live on PyPI, initial feedback collected |

---

## Timeline Summary

- **This week:** Phase 1 (✓ mostly done)
- **Week 1-2:** Phase 2 (hardening)
- **Week 2-3:** Phase 3 (docs)
- **Week 3-4:** Phase 4 (testing + CI)
- **Week 4-5:** Phase 5 (release)

**Target Public Release:** End of week 5
