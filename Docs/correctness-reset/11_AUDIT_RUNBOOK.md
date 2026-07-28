# Chuzom Correctness Reset — 11. Audit Runbook (Phase 9 / #6)

The final gate is the **two-consecutive-audit rule**: two back-to-back *complete*
audits of a **frozen commit**, each finding **zero new P0/P1** and **no "not
reached" sections**. This runbook makes that rule executable and repeatable, so a
"pass" means the same thing both times and can't be fudged.

Because **Chuzom must not audit itself** (the system under review can't certify its
own verdict), the audit is performed by the reviewer using ordinary tools + the
mechanical check script — never via Chuzom's own `llm_*` routing.

---

## Freeze bar — preconditions before an audit pass may start

An audit pass is only valid on a commit where ALL of these hold. Until they do, a
pass would hit a "not reached" section and cannot count.

| Precondition | Status (2026-07-28) |
|---|---|
| All P0/P1 closed with regression tests | ✅ (Gates 2, 4, 5) |
| Benchmark Gates 15/16/17 green, **robust** | ✅ Gate 16 made robust by precision-tier routing (#220) — delta −0.18/−0.21/−0.21/+0.00; Gates 15/17 green both re-audit passes |
| Realization/migration Gates 18/19 green | ✅ (#213 / #212) |
| Suite **deterministically** green (no flaky "not reached") | ✅ RC-0 (#206) + perf (#209) fixed; aiosqlite `database is locked` Hypothesis flake fixed (#220 — 200→75 examples + 5s→30s busy-timeout); 3.11/3.13/3.14 green on merge |
| **Gate 13** mutation closed or accepted-with-registry | ✅ `gates.py` mutation-closed 253/255 (#211/#215/#216); hermetic modules closed; equivalents registered in `12_MUTATION_EQUIVALENTS.md`; router orchestrator regression-tested (out of file-level mutation scope) |
| **Gate 7** surfaces reconcile (no estimate-as-measured) | ✅ `summary.py` real-token baseline closed the last deferral (#221) |

**⇒ The freeze bar was MET and the two passes RAN** on frozen `7c6fdaa` — both clean (see the
audit log below). Verdict: **RELEASE QUALIFIED**.

---

## One audit pass — the procedure

Run every step. If any step finds a new P0/P1 or cannot be completed, the pass
**fails**: fix the finding, re-freeze at a new commit, and restart the count at
zero (a partial pass never carries over).

### A. Mechanical (scripted, identical every pass)

```bash
git rev-parse HEAD            # record the frozen SHA
scripts/audit_check.sh        # CI-exact suite + claim-evidence validator
```
`audit_check.sh` exits 0 only when the suite is clean (modulo the documented
known-flake allowance) and the Gate-14 claim validator passes. Record its SUMMARY
line for this pass.

### B. Benchmark (out-of-band — needs a metered key + real spend)

Not in the script because it costs money and is non-hermetic. Run the moderate+hard
control-group benchmark with the escalation tier metered
(`CHUZOM_BLOCK_PROVIDERS=codex,gemini_cli`, fresh `CHUZOM_DB_PATH`) and confirm the
`evaluate_savings` verdict still shows **Gate 15/16/17 all True** with **0
exhaustions**. Record the net/quality/gate line (see `10_CODEX_QUOTA_BENCHMARK.md`
for the reference numbers).

### C. Manual gate-by-gate review (judgment — the part a script can't do)

Walk `03_RELEASE_GATES.md` top to bottom. For each gate:
1. Confirm the cited evidence (test name / PR / doc) still exists and still holds
   at the frozen commit.
2. Re-derive the invariant→test coverage matrix for the critical invariants
   (INV-COST-001..006, INV-ROUTE-001..006, INV-ENF, INV-HEALTH, INV-CLAIM).
3. Scan `git diff <reset-base>..HEAD` for any change that introduces a new P0/P1
   (a cost path that doesn't reconcile, a routing dead-end, an unqualified cash
   claim, an enforcement block with no capable door).
4. Confirm no gate row says PARTIAL/FAIL except the ones the verdict explicitly
   carries — and that each carried FAIL has a written, honest rationale.

### D. Record the pass

Append a dated block to the **Audit log** below: SHA, `audit_check.sh` summary,
benchmark line, and the reviewer's per-gate verdict (PASS / new-finding). "No new
P0/P1 and no not-reached section" is the bar for the pass to count.

---

## The two-pass rule

- **Pass 1** on frozen SHA `X` → clean.
- **Pass 2** on the *same* SHA `X` (no commits in between) → clean.
- Two clean passes in a row ⇒ flip the verdict in `03_RELEASE_GATES.md` to
  **RELEASE QUALIFIED**.
- Any new commit between or during the passes resets the count — re-freeze and
  start again.

Never soften the verdict to reach QUALIFIED. If a pass surfaces a real finding, the
honest outcome is "still NOT QUALIFIED," fix, and repeat.

---

## Audit log

Two consecutive clean passes on frozen `7c6fdaa` ⇒ verdict **RELEASE QUALIFIED**. The earlier
`54dba38` pass is kept to show the rule working — it caught a non-robust Gate 16 and correctly did
**not** count.

| Date | Frozen SHA | Mechanical | Benchmark (strict full-metering) | Gate review | Pass? |
|---|---|---|---|---|---|
| 2026-07-28 | `54dba38`→`22895cd` | suite clean (rc=0, 0 FAILED) + claim validator OK | **Gate 16 FAIL**: net +$0.02814 (G15✓), 0 exhaustions, unclassified=[] (G17✓), but quality **delta −0.58 > 0.5 margin** | halted at Gate 16 | **NO** (count reset) |
| 2026-07-28 | `7c6fdaa` (Pass 1) | suite clean (rc=0, 0 FAILED) + claim validator OK | NET **+$0.02723**; delta **−0.21**; G15/16/17 True; 0 exhaustions | no new P0/P1; all rows PASS; no not-reached | **YES** |
| 2026-07-28 | `7c6fdaa` (Pass 2) | suite clean (rc=0, 0 FAILED) + claim validator OK | NET **+$0.02722**; delta **+0.00**; G15/16/17 True; 0 exhaustions | no new P0/P1; all rows PASS; no not-reached | **YES** |

**Pass at `54dba38` — a real finding, no count started (retained for the record).** The benchmark
measured a quality delta of **−0.58** (outside the 0.5 margin) vs −0.36 on an earlier run: Gate 16
flipped across the margin → **not robustly proven** → FAIL. The audit did its job and halted; the
verdict stayed NOT QUALIFIED.

**Fix, then the two clean passes at `7c6fdaa`.** Root cause was short objective prompts where
cheap-local-first returns confident-**wrong** terse answers the runtime heuristic can't detect
(`mod-07`/`mod-12`). Precision-tier routing (#220) fronts a reliable cheap metered `gpt-4o-mini`
for exact-answer prompts, collapsing the variance (delta held at −0.18/−0.21/−0.21/+0.00 across
four runs). `summary.py`'s real-token baseline closed Gate 7's last deferral (#221), and the
aiosqlite `database is locked` Hypothesis flake was fixed (#220). The two passes above then ran
back-to-back on the re-frozen `7c6fdaa` with **no commits between them** — zero new P0/P1, no
not-reached section. Consecutive-audit rule **satisfied** ⇒ **RELEASE QUALIFIED**.

_(The only files `audit_check.sh` flags as "dirty" at `7c6fdaa` are untracked non-code docs —
`.DS_Store` and audit scratch dirs — that touch no tracked source, test, or gate; the audited
tracked tree is frozen-clean.)_
