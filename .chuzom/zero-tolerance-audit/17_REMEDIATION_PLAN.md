# 17 — REMEDIATION PLAN

Ordered by **user harm**, not by effort. Every item names the invariant it restores.

---

## Phase 0 — Today (hours)

**0.1 — Ship a security advisory.** Users are running this now against real repos with real keys.
Publish: *do not use `llm_act`/`llm_delegate` on untrusted repositories; set `CHUZOM_DELEGATE=off`.*

**0.2 — Remove the `RELEASE QUALIFIED` badge from `main`.** It is invalid on two independent
grounds (AUD-01). Leaving it up while 12 P0s are open is the single most trust-destroying item here.

**0.3 — Correct the four false claims** in README/NORTH_STAR: the FAQ "Everything stays on your
machine", "independently audited", the "live leaderboard", and "irreversible steps run in an
isolated git worktree". Wording fixes, no code.

---

## Phase 1 — Stop the bleeding (days) — restores I-6, I-7

**1.1 — Sever the injection→exfiltration chain (RED6-01 + RED6-02).** *P0.*
Two independent cuts; do **both**, since either alone leaves a live path:
- Pass an explicit **allowlisted `env=`** to every delegated subprocess. The correct helper already
  exists (`safe_subprocess.py`) — wire it into `agentic/react.py` **and** `agentic/adapters.py`
  (`CodexAdapter` bypasses the codebase's own safe `codex_agent.run_codex()`).
- Call the existing `wrap_prompt_with_boundaries`/`_is_injection_attempt` on the agentic path.
  It already works in `tools/routing.py`; it is simply not called.
- Add `env`, `printenv`, `set`, `export` to `_bash_block_reason` — but treat this as defence in
  depth, **not** the fix. A blocklist against a model that can write arbitrary shell is not a
  boundary; the allowlisted env is.

**1.2 — Stop destroying user config (RED4-01).** *P0.* Detect a foreign `statusLine`, back it up
(`_backup_before_overwrite()` already exists in the same file and is used for `chuzom.md`), and
restore it on uninstall. Record it in `install_manifest.py`.

**1.3 — Make savings honest (AUD-06).** *P0.* Remove per-item clamping; aggregate **signed** values;
render negative totals as negative. **Delete and invert the test that asserts the clamp is correct.**
Three other modules already gate on negative savings correctly — copy that behaviour.

---

## Phase 2 — Make the numbers true (1–2 weeks) — restores I-2, I-8

**2.1 — One pricing module (RED8-07, root cause of RED2-01/RED8-01/RED8-03/RED8-04).** *P0.*
Delete all five stale copies. One canonical table, imported everywhere; a CI lint that fails on any
hardcoded price literal outside it. **This is the `tool_surface.py`/CHZ-SURF-01 playbook the team has
already proven works — applied to money instead of tool names.**

**2.2 — Unknown must stay unknown (RED2-02).** Distinguish "query failed" from "genuinely zero"
everywhere. Return `None`/`Unknown`, never a zero that reads as data.

**2.3 — Reconcile the baselines (RED8-05, RED2-03, RED2-04).** One baseline policy. If quota and cash
are different units — and they are — give them different labels and never sum them. Stop showing
subscription users a cash figure the README itself says doesn't apply to them.

**2.4 — Coverage metric (I-1).** Every savings/quality surface must report *how much traffic it did
not observe*. A rate without a denominator is not a measurement.

---

## Phase 3 — Make verification mean something (2–4 weeks) — restores I-3

**3.1 — Fix ledger loss (RED5-02, RED5-01, RED5-03).** *P0.* Guard the cold-start
`PRAGMA journal_mode=WAL`. Then **check the return value** at all 7 `record_event()` call sites, and
bind the boolean at both `exclusive_lock()` sites. A success signal nobody reads is not a signal.

**3.2 — Decide what `llm_act` honestly promises (RED3-01/02/03).** *P0.* Two defensible routes:
- **Make it real**: wire the reversibility gate (worktree isolation), and stop accepting substring
  matches as proof. Verification must run on an oracle the executor cannot edit — an immutable,
  pre-registered check, hashed before execution and re-verified after.
- **Or scope the claim down**: state plainly that "verified" means "a syntactic check passed", and
  stop implying review-grade assurance.
Both are legitimate. Shipping the current wording with the current behaviour is not.

**3.3 — Close the mutation blind spots (RED-7b Q3).** Add gates that fail on: a wrong price
constant, an invalid tool name, and a wrong-signed savings total. All three currently ship green.

**3.4 — Test the artifact users receive.** `smoke-test.yml` runs the full suite against the **built
wheel** in a clean HOME, with a realistic pre-existing host config seeded (this is what would have
caught RED4-01).

---

## Phase 4 — Structural (1–2 months)

**4.1 — Fail-open policy (RED8-09).** 810 bare `except Exception`, ~234 fail-open. Triage into
*deliberate* (documented, counted, surfaced) vs *defect-masking* (delete). Ban silent swallowing in
cost, routing, and telemetry paths. **This is the mechanism that keeps every other defect invisible —
it is the highest-leverage structural fix in the codebase.**

**4.2 — Leaderboard: implement it or drop it (RED8-08).** Either make the ranking genuinely live with
a runtime staleness check and a visible warning, or delete the claim from NORTH_STAR and ship an
honest static ladder. A 4.4-month-stale snapshot presented as "continuously-updated" is the
document's own anti-goal #5.

**4.3 — Collapse duplicate classifiers (RED8-06)** and adopt one config schema (RED8-10, 186 env vars).

**4.4 — Re-qualify at the shipping SHA**, per the project's own restart-at-zero rule — and fix Gate 7,
which certified AUD-06.

---

## What to delete rather than fix

| Target | Why |
|---|---|
| `response_validation.py` | Zero production importers; docstring claims injection protection it does not provide. Dead safety code is worse than none — it reads as coverage. |
| `trace_northstar.py` (as-is) | Referenced nowhere but a CHANGELOG line. Either wire into CI or delete. |
| The clamp-defending savings test | Actively encodes a P0. |
| `gateway.py`/`route_server.py` team-server preset | Undocumented, unauthenticated, reintroduces the SEC-001 class. Delete unless someone owns it properly. |
| `secret_scrubber.scrub_environment()` | Uncalled; its allowlist is narrower than the one in use — a future foot-gun. |
| One of the three classifiers | Two are copies of ground truth nobody maintains. |

## Sequencing note

Phases 1 and 2 are independent and can run in parallel. Phase 3 depends on 2.1 (a single pricing
source) for its regression tests to mean anything. **Do not start Phase 4 refactors before Phase 1
ships** — the security chain is live today.
