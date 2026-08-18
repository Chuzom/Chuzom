# 16 — RELEASE VERDICT

**Target: `c2c28821f690f7cbda42b46da06fc36ef77d816e` — tag `v1.1.1`**

# VERDICT: NOT RELEASE QUALIFIED

Grounds: **12 P0** and **17 P1** findings survived adversarial adjudication. `RELEASE QUALIFIED`
requires zero P0 and zero P1.

## Why not "PRODUCT MODEL INVALIDATED"

Deliberately **not** the harsher verdict. The routing machinery is real and works:

- The suite genuinely passes: **6,706 passed, 172 skipped, 1 xfail, 0 failed** — not a mirage.
- **Zero** API-key-gated skips: CI is not quietly skipping the code that matters.
- **No CI masking**: every `continue-on-error` is a uv retry or a documented report-only scan.
- Python matrix **3.11–3.14** genuinely matches the README claim.
- The wheel is **complete** — 13 rules files, 3 prompts, static assets, `benchmarks.json`,
  `banner_art.txt` all present.
- Auto-delegation detectors are real, high-precision dual-signal regex detectors — not vaporware.
- Real security controls work **where wired**: structlog scrubbing, admin Bearer+RBAC, SCIM
  fail-closed with timing-safe compare, dashboard token auth, the bash destructive/credential-path
  blocklist.
- Install/uninstall/`--force`/`--purge` are genuinely idempotent; atomic writes; corrupt-JSON backup.
- **The mutation methodology works when applied**: forcing `record_event()` to return `False`
  failed **16 tests immediately**.

The premise — route cheap work to cheap models — is sound and probably does save real money for
simple/query workloads. **What fails is not the router. It is everything that reports on the router,
verifies the router, or protects the user from the router.**

## The disqualifying findings

| # | Finding | Why disqualifying |
|---|---|---|
| 1 | **RED6-01 → RED6-02** | Hostile repo content → injected instruction → shell with every API key. Demonstrated **live**, default config, default tier. |
| 2 | **AUD-06** | Reported savings **cannot be negative**. The product's own README example shows a user who spent 87% more being told they saved. |
| 3 | **RED2-01 + RED8-01** | Five stale `$15/$75` Opus copies; ≈3× overstatement on both read and write paths. |
| 4 | **RED5-02** | The canonical cost ledger drops events silently — live-reproduced, peak 29.4%, and it degrades a **spend-cap enforcement** path. |
| 5 | **RED3-01/02/03** | "DONE" is gameable by a `return True` stub or by rewriting the test; the reversibility gate protecting against it is dead code. |
| 6 | **RED4-01** | Installer permanently destroys unrelated user config with no warning and no recovery. |
| 7 | **RED1-20** | All 13 host rules files teach unregistered tool names — and both CI gates for that class pass clean. |

## The gates do not gate (§18)

Mutation testing settles this:

| Injected fault | Should be caught by | Result |
|---|---|---|
| `record_event()` → always `False` | ledger tests | ✅ **16 tests failed** — gate works |
| Opus price `15.0` → `999.0` | cost/savings tests | ❌ **0 failures** |
| Emittable tool name → `llm_bogus_xyz` | `lint_tool_surface.py` + tool-surface tests | ❌ **all green** (lint checks prose-hardcoding, not name validity) |
| Savings clamp removed | savings tests | ❌ **no test catches it — a test *asserts the clamp is correct*** |

The last row is the audit's most damning single fact. §17's standard: *a test that encodes the bug is
worse than no test.* Here a test **actively defends** the defect that makes the product's central
commercial claim unfalsifiable. Worse, RED-7b found that **three other modules gate on negative
savings correctly** — so the codebase already knows negative savings are real and meaningful, and the
one place that matters most (the user-facing display) is the exception.

**Two P0s ship with 100% green CI.** Green CI here means "no regression in what is covered." It does
not mean the product's claims are true.

## Qualification status

The `RELEASE QUALIFIED` badge on `main` is **invalid for `v1.1.1`**, on two independent grounds:

1. **Stale by the project's own rule** (AUD-01). Qualification is pinned to frozen `7c6fdaa`;
   `v1.1.1` is **125 commits / 488 files / +217,260 lines** downstream, including `router.py` +1,094,
   `tool_surface.py` +480 (effectively new), `auto-route.py` +441, `cost.py` +99. The runbook's own
   rule: *"re-freeze at a new commit, and restart the count at zero."*
2. **Insufficient when granted.** AUD-06's clamp was **present at `7c6fdaa`**, and that commit *is*
   the Gate 7 commit — Gate 7 being *"surfaces reconcile (no estimate-as-measured)."* Gate 7
   certified code structurally incapable of reporting a loss.

The badge must be removed from `main` until re-qualification is performed **at the shipping SHA**.

## Claims requiring correction before any release

| Claim | Status |
|---|---|
| "audit — RELEASE QUALIFIED" badge | **Invalid** — remove |
| "independently audited" | **Unsupported** — no third party; scope it |
| "What data does Chuzom collect? None. Everything stays on your machine" | **False** when cloud providers configured (as Get Started instructs) |
| NORTH_STAR "continuously-updated, live" leaderboard | **False** — static snapshot, `2026-03-30`, 4.4 months stale, no runtime fetch |
| "irreversible steps run in an isolated git worktree" | **False** — gate never wired (RED3-01) |
| "'Done' means the check passed, not a self-report" | **Misleading** — the planner authors the check; gameable |
| Dashboard "TOTAL … Saved" | **False** — a sum of wins, not a net |
| "Quality preserved" | **Overstated** — measured delta is −0.21, i.e. quality decreased within a margin |
| "4 independent runs" | **Overstated** — repeated measures on a corpus the fix was tuned against |

## Conditions to reach RELEASE QUALIFIED

1. All 12 P0 closed, each with a regression test proven to fail before the fix.
2. All 17 P1 closed or formally accepted with written user-visible disclosure.
3. Every claim above corrected in README/NORTH_STAR.
4. Mutation gates added for pricing, tool-name validity, and savings sign — the three proven blind
   spots. The clamp-defending test **deleted and inverted**.
5. `smoke-test.yml` runs the full suite against the **built wheel**, not an editable source install.
6. Re-qualification performed at the **shipping SHA**, per the project's own restart-at-zero rule.
7. Telemetry able to report **coverage** — how much traffic it failed to observe (I-1).

## Interim guidance for existing users

```bash
export CHUZOM_DELEGATE=off     # disables llm_act / llm_delegate
```

- **Do not run `llm_act`/`llm_delegate` against any repository you do not fully trust** — including
  one with third-party dependencies or an untrusted PR.
- **Do not use the reported savings figures for any financial decision.** They can overstate by ~3×,
  cannot go negative, and five pricing copies disagree.
- Back up `~/.claude/settings.json` before `chuzom install` if you have a custom `statusLine`.
