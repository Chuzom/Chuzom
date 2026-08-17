# 30 · The gap between "green locally" and green in CI

**Written 2026-08-17 after PR #253 returned 11 failures against a local suite of 7369
passed / 0 failed / nine gates green.**

That contradiction is the finding. This document is the plan to close it, and the record of
why the local result was worth less than it looked.

---

## 1 · The headline

**Local verification could not have caught most of this, and I reported it as though it
could.** Three of the failures depend on state that exists on the developer's machine and
not in the repository. A clean checkout was always going to expose them; nothing short of
one would have.

Corrections to claims already made in commit messages, doc 29, the changelog and the PR:

| claim made | actual |
|---|---|
| "all nine gates pass" | **G-C fails** on a clean checkout, and always would have |
| "G-C PASS" in the gate record | false — see §3 |
| "7369 passed, 0 failed" | true **on this machine**; CI fails the suite on 3.11–3.14 |

And one correction this document made about *itself*, added after the work in §3–§7:

| claim made **in this document** | actual |
|---|---|
| §6: "this is a regression from these 81 commits", "users being broken" | A quoting bug in `smoke-test.yml`; the product was never executed. **No user was affected.** See §6, §9 |
| §6: three named candidates, "test them one at a time" | All three wrong. One line of the CI log gave the cause |
| §7: "a genuine finding in new code, or a workflow/permissions issue" | Neither — 14 pre-existing alerts on `main` plus 5 in a frozen evidence tree |
| §5: "probably the same as #1" | Wrong. G-D never had the suite's env; `test` went green and G-D stayed red. **The one guess this document refused to act on is the one that was wrong** — see §5 |

---

## 2 · Status of the 11 failures

| # | check | state | root cause |
|---|---|---|---|
| 1 | `test (3.11)` `(3.12)` `(3.13)` `(3.14)` | ✅ **green in CI** | §4 |
| 2 | `G-D · wheel suite · py3.11` `py3.13` | **FIXED** — *not* the same as #1; the guess was wrong | §5 |
| 3 | `lint` → G-C step | ✅ **green in CI**, first time ever | §3 |
| 4 | `windows-latest · py3.11/3.12/3.13 · pip` | ✅ **all three green in CI** — cause was none of the three candidates | §6 |
| 5 | `CodeQL` | **red, and correctly so** — 14 alerts, all pre-existing on `main`, zero new | §7 |

Passing throughout: ubuntu and macos on 3.11/3.12/3.13 (pip and uv), docker-build,
pip-audit.

> **Update — all five diagnosed, 2026-08-17.** §6 and §7 were written as open
> questions and are now answered, both differently from how this document
> guessed. The corrections are recorded inline in §6 and §7 rather than edited
> away, because *what the wrong guesses were* is the more useful record.
>
> One finding outranks the individual fixes: **§6 was never a product defect.**
> All three Windows legs died on a quoting bug in the workflow's own inline
> Python — the interpreter raised `SyntaxError` before reaching chuzom. No
> Windows user was ever affected. §9's release position was written on the
> assumption that this was "users being broken", and that assumption was wrong;
> see §9.

---

## 3 · G-C — a hard gate that has never actually passed

```
MISSING (recorded but gone): evidence/red2/DAMAGE_usage.db.20260811_133939.db
MISSING (recorded but gone): evidence/red2/DAMAGE_usage.db.20260811_133939.db-shm
MISSING (recorded but gone): evidence/red2/DAMAGE_usage.db.20260811_133939.db-wal
MISSING (recorded but gone): evidence/red2/PRE_REPAIR_usage.db.20260811_134824.db
```

`CRITERIA_MANIFEST.sha256` records four `.db` files that `.gitignore:165` excludes:

```
.chuzom/zero-tolerance-audit/evidence/**/*.db
```

They exist locally (2 × 63MB plus WAL/SHM), so local verification finds and hashes them.
They are not in the repository, so CI cannot.

**I re-baselined with `--write` roughly a dozen times this session**, each time recording
those local-only files, then ran the verify and called it green. The gate's own error text
is explicit about why that is wrong:

> *"If a change was deliberate, re-baseline with `--write` IN ITS OWN COMMIT so the edit to
> the oracle is visible in review."*

Folding a re-baseline into a feature commit is exactly what makes an oracle edit invisible,
and I did it every time.

### Fix

The manifest must record **only tracked files**. `git ls-files` is the authority, not
`Path.rglob`. Two properties to preserve:

- a file that is tracked and changes → G-C fails (the point of the gate);
- a file that is untracked → never recorded, so it can never produce a MISSING that only
  reproduces on someone else's machine.

**This is a change to the audit's own oracle and goes in its own commit**, per the gate's
instruction, with the re-baseline visible as a separate diff.

Open question for review: those four `.db` files are genuine incident evidence (the damaged
and pre-repair copies of the operator's real database from AUDITOR_INCIDENT.md). They are
correctly gitignored — 127MB of a user's real usage data has no business in a public repo.
So they cannot be tracked, and the manifest must stop pretending they are.

### Resolution — DONE, verified in a clean clone

The open question above is answered by **keeping the hashes but not gating on them**.
Deleting them outright would make "too big to commit" mean "unverifiable", which the
original comment in the script was right to refuse. The manifest now has two sections:

```
171 gated (tracked)      — compared; drift here fails the build
  4 recorded, not gated  — evidence/red2/*.db{,-shm,-wal}
```

The split is **structural** (a section header), not a per-line `[untracked]` tag — a tag can
be typed onto a line by a later edit and silently move a file out of the gated set.

Two guards against the same failure returning quietly: if `git` is unavailable the script
**fails** rather than falling back to a filesystem walk (the fallback *is* the bug), and a
gitignored path found in the gated section is reported as such with the fix, instead of as a
bare `MISSING` — that message is what sent this document's author hunting for drift that did
not exist.

Oracle change and re-baseline are two commits, per the gate's own instruction. **The
re-baseline changed no digest**: 175 `(digest, path)` pairs before, the same 175 after, none
added, none removed — only their section. That pairwise check is worth running on any G-C
re-baseline; it separates "the manifest was restructured" from "criteria changed under cover
of a restructure", and only the first is reviewable at a glance.

Verified in a real `git clone` with zero `.db` files present — the exact condition that broke
CI — plus six controls: modified / deleted / added tracked criteria each still **fail** the
gate; restored baseline passes; `git` missing and not-a-repo both **exit 1** rather than
silently passing. The last two matter because the first attempt at that control measured
`tail`'s exit status instead of the script's and read as a false pass — §8's pattern, live,
inside the verification of §8 itself.

---

## 4 · The quality-guard test — green for a reason unrelated to the code

```
FAILED tests/test_quality_guard.py::TestQualityReorderingIntegration
       ::test_routing_decisions_are_logged - assert 0 >= 1
```

`tests/test_quality_guard.py` writes to the database throughout and used the `temp_db`
fixture **zero times**, despite that fixture's docstring saying it "MUST be used by any test
that writes to the database (including `log_routing_decision`)".

This is the module finding #30 traced as the source of 28,536 synthetic rows in the
operator's real `usage.db`. The P0 fix made `cost.log_routing_decision` call
`_refuse_unisolated_test_write()` and return early. So the test now writes nothing — and
still passed locally, because it counts rows matching `openai/gpt-4o` and the developer's
real database holds **4,440** of them from genuine traffic.

**Fixing a P0 exposed a test that was only ever green because of the pollution that P0
described.** The pollution was the passing condition.

### Fix — DONE, verified

An `autouse` fixture pulling in `temp_db` for the whole module. Autouse rather than
per-test, because a test added later would inherit the same trap.

Verified by control: `HOME=/tmp/clean_home_probe2 pytest tests/test_quality_guard.py` →
**18 passed**, where the same command before the fix reproduced CI's `assert 0 >= 1`
exactly.

---

## 5 · G-D — probably the same, and that word is doing real work

G-D runs the full suite on the built wheel, so if §4 was the only suite failure it should
clear too. **Not verified.** Every diagnosis-by-reading this session has been wrong — nine
refuted hypotheses on the hook stall alone — so this stays a hypothesis until CI says
otherwise.

### Still a hypothesis — and the evidence gathered does not upgrade it

The full suite now passes under an environment reconstructed from `ci.yml` rather than
invented: clean `HOME`, leaked `*_API_KEY` variables unset, the dummy `OPENAI_API_KEY` that
workflow sets, and the same `--ignore` / `--timeout` flags.

```
7368 passed, 173 skipped, 0 failed    (pytest exit 0)
```

That is real evidence that §4 was the only suite failure, and it is **not** evidence that G-D
passes. G-D deliberately runs a different invocation — `-o pythonpath=` with
`CHUZOM_REQUIRE_WHEEL=1`, so `chuzom` must resolve from site-packages — precisely because the
ordinary run cannot see packaging defects: missing `package_data`, modules absent from the
wheel, entry points that do not resolve, hook scripts not shipped. `src/chuzom/hooks/*.py` are
executed as standalone scripts by path, which is exactly the shape that works in-tree and
breaks when packaged.

A suite that passes against the source tree is the *same class of evidence* this document
opened by rejecting. So the label does not change: **hypothesis until the wheel job says
otherwise.** If it fails, read its log first — that is what worked for §6 and §7.

### The hypothesis was wrong — FIXED, and the caution was worth it

CI said otherwise. §4's fix landed, `test` went green on all four versions, and **G-D stayed
red** — on something with no connection to §4:

```
ValueError: No providers available for query/budget. Configured providers: none
```

41 failures across `test_t3_m1`, `test_t3_m2`, `test_t3_m4`, `test_t3_s2`, `test_t4_m1`,
`test_t4_m2`. Nothing about wheels, packaging, or anything G-D exists to detect.

`ci.yml`'s `test` job sets a dummy `OPENAI_API_KEY`, with a comment explaining that a
routing-audit fix to `_build_and_filter_chain` made these modules require a non-empty provider
list — they patch the dispatch layer and never make a network call, but they need *some*
candidate in the chain, and a bare runner has no keys and no Ollama. `smoke-test.yml`'s
wheel-suite job never got it. **Two jobs running the same suite; one of them configured.**

Confirmed rather than assumed: the failing *file set* is byte-identical to the one produced
locally by running the suite without that key — 41 on CI against 38 locally, the difference
being `providers: none` there versus one leaked key here.

**This is the entry that justifies the whole document.** §5 refused to call G-D fixed on the
strength of a plausible inference, and the inference was wrong. Had it been reported as
"likely fixed", the actual defect — a gate that has never run in a valid environment — would
have shipped behind a green-looking summary.

#### And an uncomfortable note

Those 38 local failures appeared earlier in this work and were written off as an artefact of a
botched "clean HOME" probe (§8). That dismissal was **right about the probe and wrong about
the signal.** The same misconfiguration was sitting in G-D the entire time, and an accidental
exact reproduction of a real defect was filed as noise.

So §8's pattern has a mirror image worth naming: *a measurement known to be flawed can still
be measuring something real.* "My probe was wrong" answers where the number came from — it
does not answer whether the number is also true somewhere else.

#### Guard

`scripts/lint_suite_env_parity.py` — every step running the whole suite must set the shared
environment, by value, not merely by presence.

It took three passes to get right, which is the point. The first two flagged `routing-hermetic`
(which runs with **no** keys deliberately, selected by marker, and would have been broken by
"fixing" it) and G-D's `uv pip install … \` continuation, where the bare word `pytest` lands on
a line carrying no install marker. A lint with false positives gets its baseline padded until
it detects nothing — the exact failure it was written to prevent. Verified by control: exit 1
against the pre-fix tree naming exactly the one real step, exit 0 after.

---

## 6 · Windows — undiagnosed, and unreproducible here *(diagnosed; see below)*

All three legs fail; all three **passed on `main`** at `c2c28821` (v1.1.1), so this is a
regression from these 81 commits and not pre-existing.

I have no Windows machine. This cannot be reproduced locally at all, which makes it a
push-and-read-CI loop.

Candidates, explicitly unverified and listed in the order I would test them:

1. `tests/test_hook_emits_before_accounting.py` — spawns a subprocess with a
   `sitecustomize` shim and manipulates `PYTHONPATH` with `os.pathsep`. Newest, most
   platform-sensitive thing added.
2. `scripts/lint_state_root.py` — path handling, `Path.home()`, and a check for the literal
   `"~/.chuzom"` that would not match a Windows spelling.
3. `tests/test_hook_self_timing.py` — loads a dash-named script via `importlib`.

**Do not fix all three speculatively.** Push one, read CI, repeat. Speculative fixes to an
unreproducible failure are how a real cause gets buried under three unnecessary changes.

### What it actually was — FIXED

**All three candidates above were wrong, and the log said so in one line.** The advice not to
fix them speculatively was right; what it missed is that no fix was needed at all, because
the failing job never reached chuzom.

```
File "<string>", line 25
  assert after.get('model') == 'opus', f'install() clobbered model: {after.get(\
                                       ^
SyntaxError: unterminated string literal (detected at line 25)
```

`.github/workflows/smoke-test.yml` runs inline Python via `python -c "…"`. `run:` uses **bash**
on ubuntu/macos and **pwsh** on windows. bash collapses `\"` inside a double-quoted string to
`"`; pwsh does not treat backslash as an escape character at all, so the backslashes survive
verbatim into the Python source. The same block is valid on every platform the developer can
reach and a parse error on the one they cannot.

The job's step list is unambiguous: steps 1–11 all `success`, step 12 the only `failure`. The
product was never executed.

Fixed by hoisting the values into locals, which removes the need for nested quotes. Guarded by
`scripts/lint_workflow_shell_portability.py`, which fails any `run:` block using `\"` without a
pinned `shell:`. **Verified by control against the pre-fix tree** — it reports exactly the two
lines that broke CI, so it detects the defect it is named for rather than a synthetic
stand-in, which is the distinction commit 82d574a was about.

Two things worth keeping from this:

- **"Unreproducible locally" and "undiagnosable locally" are different problems.** This one
  could not be reproduced on any machine here and was fully diagnosed from CI's own log in
  under a minute. Reading the log cost less than any of the three candidate fixes would have.
- **§9 is wrong about this failure.** See §9.

---

## 7 · CodeQL — neither of the two guesses

Not yet examined. Could be a genuine finding in new code, or a workflow/permissions issue on
a first-time branch push. Read it before assuming either.

### What it actually was — RESOLVED

Neither. The check reported *"19 new alerts including 18 high severity security
vulnerabilities"*, which read literally is alarming. It splits cleanly in two:

| count | where | what it is |
|---|---|---|
| 14 | `src/` — `context.py`, `compaction.py`, `router.py`, `code_context.py`, `okf.py`, `session_store.py`, `doctor.py`, `hooks/auto-route.py` | **pre-existing**, already open on `main` |
| 5 | `.chuzom/zero-tolerance-audit/evidence/` | frozen forensic artifacts |

The first group is CodeQL saying so itself in its own summary — *"Alerts not introduced by
this pull request might have been detected because the code changes were too large"* — and an
81-commit branch is exactly that case. Confirmed by diffing the PR's annotations against the
40 alerts open on `main`. **Not suppressed**: they are real, still open, and separate work.

The second group is the evidence tree: the hook scripts as *deployed* at the time of the
AUDITOR_INCIDENT (snapshots, not copies — they differ from `src/chuzom/hooks/` by ~250 lines),
plus a PoC whose entire job is to exhibit an error-sanitization gap. Scanning it cannot yield
an actionable finding: every alert is either a defect already adjudicated and fixed in live
code, or one deliberately reproduced to document it. "Fixing" the PoC would delete the
demonstration it exists to preserve. None of it ships — `pyproject` packages `src/chuzom` only.

Fixed by `.github/codeql/codeql-config.yml` with `paths-ignore` scoped to that tree, and
nothing else. A security exclusion should never be read wider than it is: this suppresses
**scanning of a historical snapshot**. It does not fix, dismiss, or excuse anything live.

Also found while there: the `continue-on-error` comment on the CodeQL job is stale. Code
scanning is now enabled and SARIF uploads succeed, so the 403 it was written for no longer
happens. It is deliberately **kept** — `main` carries ~40 open alerts, and removing it today
would make CodeQL block on that backlog rather than on new findings. Triaging that backlog and
then removing the flag is a real piece of follow-up work, not a side effect of this PR.

### Confirmed by CI, and the "pre-existing" claim tightened

The exclusion worked: **19 alerts → 14**, all five evidence-tree alerts gone, no `src/` alert
suppressed. The `codeql` job passes. The `CodeQL` results check **still fails**, on the 14.

The claim that those 14 are pre-existing was originally made on *path-level* matching —
"these files already have open alerts on `main`" — which is weaker than the claim needed to be,
because a file can carry an old alert and a new one at once. Re-checked at full
`(path, rule_id, line)` precision against the 40 alerts open on `main`:

```
exact (path, rule, line) match on main : 14
same path+rule, different line         :  0
not on main at all                     :  0
```

**This branch introduces zero new CodeQL findings.** The check is red because CodeQL's
diff-scoping cannot attribute alerts across an 81-commit branch and says so in its own summary.

That makes `CodeQL` red for the same reason G-C was red before §3: **the check is reporting on
something other than the change it is gating.** The difference is that G-C's version was a bug
in our oracle and fixable; this one is a real scanner correctly reporting a real backlog, mis-scoped.
So the resolution is different — not a fix, but a decision recorded in §9 with the evidence
above attached, and the backlog itself triaged as its own work.

---

## 8 · The general lesson, which outlives these eleven failures

Three separate checks were green locally for reasons that had nothing to do with the code:

- **G-C** — passed on 127MB of gitignored evidence on one disk;
- **the quality-guard test** — passed on 4,440 rows of the developer's real routing history;
- and earlier the same day, **a regression test of mine** passed against the reverted code
  because its shim never took effect.

The shape is identical each time: *the check compared something to itself, or to local state
that is not part of the artefact.* This audit found four instances of that pattern in the
codebase today and ran two of its own without noticing.

### Two more instances, both produced while fixing the four above

The pattern did not stop once it had been named in writing. Both of these happened during the
work in §3–§7, *after* §8 existed:

- **A control that measured the wrong process.** Checking that G-C exits non-zero when git is
  unavailable, via `script … 2>&1 | tail -2; echo $?` — which reports **`tail`'s** exit
  status, not the script's. It printed `exit=0` next to the word `FAIL` and would have been
  recorded as "the failure path is broken" had the contradiction not been visible on the same
  screen. Re-run without the pipe: exit 1, correct. *A test harness is an artefact and needs
  the same scrutiny as the thing it tests.*
- **A "clean HOME" that was not clean.** `HOME=/tmp/empty pytest` produced 38 failures that CI
  does not have. Cause: the clean HOME strips `~/.chuzom` config, so the provider set collapsed
  to whatever `*_API_KEY` variables leaked in from the interactive shell — CI sets a dummy
  `OPENAI_API_KEY` for exactly this reason, and `ci.yml` documents it. Changing one variable
  does not make an environment clean; **it makes a third environment, resembling neither the
  developer's nor CI's.**

The second is worth stating plainly because §4 uses `HOME=<clean>` as its verification method
and that method is sound *there* — for a single module whose failure is caused by database
state in `$HOME`. It is not sound as a whole-suite substitute for CI. The generalisation is
the error, not the technique.

**Corollary to "a local suite is evidence about one machine":** so is a local *approximation*
of CI. Reproduce CI's environment from its workflow file, or read CI's log — do not invent a
third environment and reason from it.

### What actually diagnosed four of the five failures

Reading the CI log. Not local reproduction, and not the candidate lists in §5–§7 — every one
of which was wrong. §6's three suspects: all wrong, one log line gave the true cause. §7's two
possibilities: both wrong, the check's own summary text gave the true cause. The document was
right that speculative fixes bury real causes; what it under-weighted is that **the evidence
was already sitting in CI's output** while the plan was proposing to guess.

**A local suite is evidence about one machine.** The only thing that tests the repository is
a clean checkout. Nothing in this document is a criticism of CI being slow — CI caught what
a day of local verification could not.

---

## 9 · Release position

`v1.2.0` should **not** merge in this state.

The distinction worth keeping: **G-F NOT QUALIFIED is a measurement gap** — the product
works, one property cannot be certified, and that is honest to ship. **A Windows regression
across three Python versions is users being broken**, and G-C red would make a hard gate
decorative, which is the failure this audit exists to prevent.

Order of work: §3 (its own commit) → push → read CI → §6 one candidate at a time → §7.

### Revised — the Windows premise was false

The paragraph above is right about G-C and **wrong about Windows**, and the two were weighted
against each other, so the conclusion needs restating rather than just updating.

There was no Windows regression. All three legs died with `SyntaxError` in the workflow's own
inline Python, at step 12 of 12, with steps 1–11 green — the interpreter never reached chuzom.
Nothing shipped to a user was involved and no Windows user was ever affected. "Users being
broken" described a test harness that could not parse its own script.

That leaves G-C as the only argument in that paragraph that survives, and it is a strong one:
a hard gate that has never actually passed *is* decorative, and that is the failure this audit
exists to prevent. It is now fixed and verified against a real clean clone rather than against
this disk — which is the first time the gate's result has been a statement about the
repository at all.

**Revised position:** the four blocking failures are fixed, each verified by a control that
distinguishes the fix from a coincidence. What remains before merge is not analysis, it is
**CI confirming it on a clean checkout** — including §5 (G-D), which is still a hypothesis and
should stay labelled one until the wheel job says otherwise. The honest summary is not "ready
to merge"; it is *"nothing further is diagnosable from here — push and read CI."*

### Position after CI · 31 of 34 green

CI confirmed four and refuted one, which is the correct return on refusing to over-claim:

| | |
|---|---|
| `test` × 4 | ✅ green — §4 fixed |
| `windows` × 3 | ✅ green — §6 was never a product defect |
| `lint` (G-C) | ✅ green — **the first time this gate has ever passed** |
| ubuntu/macos × 12, +12 others | ✅ green |
| `G-D` × 2 | ❌ → **fixed after CI refuted §5's guess** — awaiting re-run |
| `CodeQL` | ❌ **red on 14 alerts, all verified pre-existing on `main`, zero new** |

**Merge position: unblocked on the merits, with one red check that is a judgement call and
not a defect.**

Every failure that described something broken is fixed. The single remaining red is `CodeQL`,
and its redness has been measured rather than argued: all 14 alerts match `main` at
`(path, rule, line)`, none are new, and CodeQL states in its own summary that it cannot
diff-scope across a branch this size. Merging means accepting that. Declining to merge on a
red check is also defensible — the answer to it is triaging `main`'s 40 alerts, which is its
own work and not this PR's.

The `v1.2.0` hold in the original §9 rested on two arguments. The Windows one was false. The
G-C one was true, and is now fixed and verified against a real clean clone rather than this
disk — which is the first time that gate's result has been a statement about the repository.

What earned its keep here was not the fixing. It was §5 declining to call G-D fixed on a
plausible inference. That inference was wrong, and had it been reported as "likely fixed", a
gate that has never once run in a valid environment would have shipped behind a green summary.

Two things deliberately **not** fixed, recorded so they are decisions rather than omissions:

- ~40 pre-existing CodeQL alerts on `main`, 14 of which this PR's check reports. Verified at
  `(path, rule, line)` precision: **all 14 are exact matches on `main`, none new.** Real, still
  open, out of scope for a PR about CI failures — but they are the reason the CodeQL job keeps
  `continue-on-error`, so triaging them is what unblocks making CodeQL a required check.

  **`CodeQL` will therefore still be red at merge time**, and that is a judgement call, not a
  fix: merging means accepting a red check whose redness has been shown to be about `main`'s
  backlog rather than this branch. Anyone who prefers not to merge on a red check has a fair
  objection — the answer to it is triaging the 40, not anything further in this PR.
- The four gitignored `.db` captures remain unverifiable by anyone who does not hold them.
  Recording their hashes is the most that can be done without putting 127MB of a user's real
  usage data in a public repo.

Revised order of work: §3 ✓ → §4 ✓ → §6 ✓ → §7 ✓ → **push → read CI** → §5 confirmed or
diagnosed from the log, not guessed at.
