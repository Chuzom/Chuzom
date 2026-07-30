# Chuzom Release Convergence — Final Assessment

**Verdict: BLOCKED** (for a "fully converged / clean" claim) — the adversarial loop ran its full 8-iteration budget and **never produced a clean RED round**, so the required "2 consecutive clean rounds with no code change between them" was not met.

This verdict is about the *convergence bar*, not the product's health. The practical release posture is strong and the residual risk is characterized and bounded (see below).

## What the loop did

8 iterations, each: two INDEPENDENT adversarial auditors (RED-1 architecture/correctness, RED-2 customer-reality) → PLAN adjudication (every finding reproduced before acceptance) → FIX (test-first) → GATE (full suite). No finding was accepted on an auditor's claim alone; the headline Criticals were independently re-reproduced.

| Iter | RED findings | Criticals | GATE after fixes |
|------|-------------|-----------|------------------|
| baseline+1–3 | 26 fixed | (mitigation of the original 1.0.0 audit) | green each |
| 4 | (diagnosis) | — | 6408/0 — proved the "11-test regression" was a leaky TEST, not product code |
| 5 | 7 | **1** (envelope commit double-decrement → 150% cap breach) | 6428/0 |
| 6 | 5 | **1** (hook auto-update version-gated → fixes never reached installed users) | 6449/0 |
| 7 | 4 | 0 (settle atomicity, backup-on-overwrite, uninstall entrypoint, carve-out) | 6458/0 |
| 8 | 6 High + 2 Med | 0 (rejected-attempt billing, backup safety, drain-lifespan, banner honesty, postgres-warn) | **6466/0** |

Full per-iteration reports, adjudications, and gate logs are under `iteration-0N/`.

## Severity trajectory (the real signal)

Criticals per round: … → **1 → 1 → 0 → 0**. The two Criticals were genuinely new, deep subsystem defects (a shared-cap breach in the distributed budget envelope; the entire hook-delivery path silently not shipping fixes — including security fixes — to installed users). The last two rounds found **zero** Criticals; their findings are increasingly refinements of already-hardened code. That is the shape of a codebase *approaching* convergence — but "approaching" is not "converged," and the bar is two clean rounds.

## Why it did not fully converge

Two recurring theme areas keep yielding findings that point-fixes cannot close:

1. **The multi-host install/uninstall surface is structurally incomplete.** `install --host` writes to Claude Code, Claude Desktop, claw-code, codex, cursor, gemini-cli, vscode, windsurf, opencode, copilot, trae — but `uninstall` was assembled ad hoc and misses subsets every round (iter5 statusline+sidecars, iter6 the whole claw-code path, iter7 the sibling entry point, iter8 all the `--host` MCP registrations). **This will keep recurring until there is a single source-of-truth manifest**: `install` records every path+block it wrote; `uninstall` consumes it. That is the one remaining **release-blocking** item (RED2-8-01): a user who ran `chuzom install --host codex/cursor/…` then `chuzom uninstall` is left with live/dangling `chuzom` MCP registrations that break those tools after `pip uninstall`.

2. **Budget-accounting edges** yielded one finding most rounds (double-decrement, release-then-commit race, rejected-attempt under-count) — all now fixed, but the subsystem's scattered reserve/release/settle sites (documented since iter4) remain more fragile than a single-owner lifecycle would be.

## Residual risk after iteration 8 (honest ledger)

| Item | Sev | State | Impact |
|------|-----|-------|--------|
| RED2-8-01 uninstall misses `--host` MCP registrations | High | **DEFERRED** — needs the install/uninstall manifest refactor | Dangling MCP entries break codex/cursor/gemini/vscode after `pip uninstall`. NOT a security or spend issue. The one item that should gate a *wide* 1.0.1 release. |
| RED1-8-04 Postgres forecast tier absent | High | Mitigated (warns+alerts on select); full port DEFERRED | Postgres backend is EXPERIMENTAL; strict-forecast throttle inert there (hard cap still enforced). |
| Reservation single-owner refactor | — | Documented since iter4 | All known instances fixed; design still scattered. |

Everything else the 8 rounds surfaced (2 Criticals + ~24 Highs + several Mediums) is **fixed and GATE-green (6466/0/0)**, each with a data-backed regression test.

## Recommendation

The convergence workflow's strict gate is **BLOCKED**. For the actual ship decision, the choice is the user's:

- **(A) Recommended:** do the **install/uninstall manifest refactor** (a focused, dedicated change that also structurally ends the recurring uninstall findings), then run one more RED round to confirm clean, then ship 1.0.1.
- **(B)** ship 1.0.1 now with RED2-8-01 documented as a known limitation (uninstall doesn't clean `--host` tool registrations; workaround: remove the `chuzom` MCP entry manually) — acceptable if few users use `--host`.
- **(C)** continue the audit loop beyond the 8-iteration budget.

The original 1.0.0 blocking audit is fully mitigated; the campaign then went deeper and fixed two more Criticals. The product is materially safer than 1.0.0. It is not *certified clean* by the two-clean-rounds bar, and this document says so plainly rather than claiming a RELEASE CANDIDATE it did not earn.

_Credential-gated (user action): yank 1.0.0 / publish 1.0.1 to PyPI — not performed here._
