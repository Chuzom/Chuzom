# 20 · Protocol for a legitimate G-F qualification

Status: **PRE-REGISTERED**. Authored 2026-08-13, *before* any remediation work
begins. Sealed by `CRITERIA_MANIFEST.sha256` and checked by G-C in CI, so any
later edit to this document is visible in review.

Design informed by an independent review routed to `codex/gpt-5.5`; sample-size
arithmetic, runtime budget and tooling choices verified against this repository.

---

## 0 · The rule, and why the obvious path is not available

G-F: `score ≥ max(baseline + 0.15, 0.80)`. Baseline is **0.12**, so `+0.15`
gives 0.27 and **the floor dominates: 0.80 absolute.**

The baseline-era sample would now read ~0.50 (B1/B4/B9 closed), and covering
B6/B7/B10 plus correcting B8's test-ownership metadata would put it near 1.00.

**That number would be inadmissible.** It fixes the survivors of the sample it is
graded on. It is the same error as the original frozen ten scoring 1.00 — an
instrument calibrated on the defects the work had just fixed — one level down.
Producing it and calling it a pass would make this document pointless.

**The known survivors are diagnostics, not a checklist.** They name weakness
*classes*: a degraded state reported clean (B6), a persistence path not verified
(B7), a neutral/default state inverted (B10). The work is to cover those classes
across the codebase, not those three lines.

## 1 · Instrument

**Use `mutmut` 3.6.0.**

> **CORRECTION (Phase 0, measured).** This section originally said mutmut "was
> never wired to anything", quoting `scripts/mutation_sample.py`'s docstring. **That
> claim is false, and I repeated it without checking.** `setup.cfg` carries a
> `[mutmut]` section wiring six files with explicit per-file test selection, and
> mutmut **runs**: it generated **1214 mutants in 2.5s** and began executing them.
>
> What is true is narrower: **exactly one of those six files (`execution_ledger.py`)
> is in G-F's scope.** Seven of the eight scope modules are unmutated, and
> `bench/savings.py` in that list is a *different file* from `src/chuzom/savings.py`.
>
> So Phase 0's task is to **rescope**, not to wire from nothing. Taking a docstring's
> claim at face value is the same error this audit keeps recording; it is recorded
> here rather than quietly edited.

This replaces hand-authored samples for *scoring*. Hand-authored mutations cannot
reach the sample sizes below, and a human choosing them is the selection bias
this protocol exists to remove.

`scripts/mutation_sample.py` is **retained** for targeted diagnostics — its
behaviour probes, `EQUIVALENT`/`UNVERIFIED` classification and uniqueness
enforcement are useful when investigating one defect. It is **not** the scoring
instrument.

**Target modules** (the gate's stated scope), with current size:

| area | modules | loc |
|---|---|---|
| money | `cost.py`, `savings.py`, `execution_ledger.py` | 4,323 |
| routing | `router.py`, `tool_surface.py`, `classify.py` | 6,215 |
| verification | `budget.py`, `coverage.py` | 716 |

## 2 · Three-way split, sealed

Generate the full mutmut universe over those eight modules at a frozen SHA, then
split it **deterministically** before any test is written:

```
seed = sha256("chuzom-gf-v1" + baseline_sha + universe_manifest_sha)
shuffle(universe, seed) → 60% TRAIN · 20% VALIDATION · 20% HOLDOUT
```

Stratify by `(module, operator)` so the holdout cannot end up dominated by one
file or one mutation kind.

- **TRAIN** — inspect freely. This is where the work happens.
- **VALIDATION** — score periodically. Feedback on whether improvements
  generalise beyond train.
- **HOLDOUT** — **scored exactly once, at the end.** Never inspected.

**Sealing.** Commit only `holdout_manifest.sha256` and the seed inputs — not the
holdout mutant IDs. G-C already fails CI on manifest drift, so the seal is
tamper-evident without new machinery. The encrypted-secret approach the routed
review suggested is over-engineering for a single-maintainer repo; the property
that matters is that a later edit is *visible*, and G-C gives that.

## 3 · Sample size, with the arithmetic

A pass must survive its own error bars. For a binary killed/survived proportion,
`SE = sqrt(p(1−p)/n)`, and the gate should require the **95% lower bound** ≥ 0.80,
not the point estimate.

| holdout n | at p=0.85 | at p=0.90 |
|---|---|---|
| 120 | lower bound **0.786** ✗ | lower bound 0.846 ✓ |
| 150 | 0.793 ✗ | 0.852 ✓ |
| 200 | **0.800** ✓ | 0.858 ✓ |

**Decision: holdout n ≥ 150, and the gate requires the 95% lower bound ≥ 0.80.**
That forces a true score near 0.88+ rather than a bare 0.80 — which is the
correct direction for a floor that exists to be hard.

**REVISED TWICE (Phase 0, both measured).**

*First:* the universe is far larger than the ~750 first assumed — mutmut produced
**1214 mutants from six files** in 2.5s, and G-F's eight modules are bigger.

*Second, and it changes the design:* throughput is **14.13 mutations/second**,
measured over a complete 1214-mutant run (737 killed / 459 survived / 18
uncovered, ~86s). My earlier figure of ~36s/mutant came from the hand-rolled
harness, which runs a pytest subprocess per mutation; mutmut reuses a warm
process and runs only the covering tests.

**At 14/sec, even a 10,000-mutant universe is ~12 minutes.**

So **there is no sampling step.** Generate the full universe and split *all of it*
60/20/20. This is strictly better than sampling:

- no sampling bias to argue about, at any stage;
- the holdout becomes **hundreds to low thousands**, not 150, so the 95% lower
  bound is tight enough that the point estimate and the bound nearly coincide;
- the whole thing is reproducible from the universe manifest alone.

The n≥150 floor in the table above therefore stops being a constraint and becomes
a *minimum* that the design clears by an order of magnitude. Keep the
lower-bound-≥0.80 rule regardless: it costs nothing when n is large and it is the
rule that makes a marginal result honest.

## 4 · Scoring rule — conservative, decided in advance

```
score = killed / total_scored          # equivalents and unverified count as SURVIVORS
```

At this scale, per-mutation behaviour probes are not written, so equivalent
mutants cannot be individually excluded. **Counting them as survivors biases the
score DOWN.** That is the safe direction: it can only make the gate harder to
pass, never easier.

If the conservative score lands within 0.03 of the bar, and only then, a
documented equivalence review may be run — each exclusion requiring the mutant
diff, the reason no valid test could observe it, and a written justification in
the artefacts. **Never as a way to reach the bar after missing it.**

## 5 · Stopping rule — fixed now, so it cannot be adjusted later

1. Work proceeds against **TRAIN** survivors and ordinary coverage reasoning.
2. **VALIDATION** may be scored after each batch of test work.
3. Stop when validation ≥ **0.88** on two consecutive runs *and* its 95% lower
   bound ≥ 0.80.
4. Run **HOLDOUT once**. No fixes between the stopping condition and that run.
5. If holdout fails: the attempt is **recorded as failed**. The holdout is then
   burned — a new round requires a **new universe, new seed, new holdout**.
   Re-running a seen holdout is the thing this whole protocol prevents.

## 6 · Order of work

**Phase 0 — trust the instrument (do first).**
Wire mutmut into a reproducible script; record commit SHA, command line,
environment and universe hash in every result. Correct B8's test-ownership
metadata in the legacy sample (`tests/test_t2_m1_budget_key.py`, not
`tests/test_budget.py`) — misattribution corrupts diagnostics. Make CI fail on
manifest drift (already true via G-C).

**Phase 1 — freeze and split.** Generate the universe, derive the seed, split,
seal, commit hashes. Score the baseline at the frozen SHA on train + validation
only. **Do not touch holdout.**

**Phase 2 — classify, don't checklist.** Group train survivors into weakness
classes. The three known ones — degraded-state-reported-clean, persistence-path
unverified, neutral/default inverted — are almost certainly systemic, not local.
Expect new product defects to fall out, as B1 did.

**Phase 3 — write behavioural tests.** Assert externally meaningful behaviour:
money invariants and boundaries, ledger read/write path correctness, routing
decisions, tier resolution, budget state transitions, degraded/empty/error
states. **Do not write tests that encode an implementation detail purely to kill
a known mutant** — that passes train and moves validation not at all, which is
exactly the signal to watch for.

**Phase 4 — verdict.** Stopping rule met → holdout once → record.

## 7 · What invalidates the result

Any one of these voids the qualification:

- the protocol was edited after work began (G-C makes this visible);
- holdout contents were inspected, or holdout was scored more than once;
- tests were added between the stopping condition and the holdout run;
- the sample was regenerated after seeing a failing score;
- equivalence exclusions were used to cross the bar rather than reviewed on
  principle;
- the score is reported without its confidence bound.

## 8 · Honest effort estimate

**Phase 0–1: half a day** plus one overnight run. **Phase 2–3: the real work.**
On 11,254 lines across eight modules with a true score near 0.12, expect
**several days to a couple of weeks** of test writing, and expect it to surface
further product defects — the last sample of ten surfaced a P0.

**This is not a formality that can be closed in a session.** If the release is
time-critical, the alternative is not a faster pass; it is an explicit, recorded
decision to amend or waive G-F's 0.80 floor — a criteria change, which is the
owner's to make and must be recorded as an amendment, never as a pass.

---

## AMENDMENT 1 — source-scanning tests are deselected from the mutation run

**Date:** 2026-08-13 · **Requested by:** owner, explicitly ("exclude the
source-scanning tests, record the amendment") · **Applies from:** Phase 1, before
any mutation score has been produced.

### Read §7 first

§7 voids this qualification if "the protocol was edited after work began". This
amendment *is* an edit after work began. It is recorded here, in the tracked and
G-C-hashed document, precisely so it shows up as one rather than hiding in a config
file — but an auditor is entitled to weigh it as a deviation, and should.

**The fact that makes it not gaming: no mutation score exists yet.** Five baseline
attempts have been made and every one died before scoring — three
`ModuleNotFoundError`s, then a pytest reporter crash. Nothing has been measured, so
this cannot be, and must not later be described as, a rule changed after seeing a
number. §7's other bullets are untouched: the split was sealed before this, the
holdout has never been read, no test has been written yet.

### What changed

Twenty-two deselections are passed to every pytest invocation mutmut makes, via
`pytest_add_cli_args` in `config/mutmut_gf.cfg`.

A test is deselected iff it either **(A)** traverses Python source files
(`rglob`/`glob` over a `*.py` pattern), or **(B)** invokes one of the repo's
source-scanning gate scripts as a subprocess. Both criteria describe a test's
**method**, never its subject. Neither asks what a test is *for*.

### Why

A mutant **is** a source edit. A test that inspects source *text* can fail simply
because the text changed, and mutmut records any suite failure as KILLED. Such a
test therefore reports a mutant "killed" when nothing about the program's
**behaviour** was detected.

It is worse than one bogus kill per mutant: mutmut's working copy holds all ~2436
mutant variants simultaneously, so a tree-scanning check can be tripped by the
presence of *other* mutants and kill a mutant whose own change was irrelevant.

That is the same defect this protocol was written to escape — a number that looks
right, is wrong, and is wrong in the direction that flatters the result.

**Measured, not argued:**

| observation | real tree | mutmut working copy |
|---|---|---|
| size of `src/chuzom` | 14 MB | 460 MB |
| AST nodes | 442k | 23.4M |
| one source walk | 0.3s | 27.7s |
| `scripts/lint_savings_sign.py` | instant | **>25 min, killed unfinished** |

With `pyproject`'s `timeout = 30`, that 27.7s walk fires pytest-timeout; SIGALRM
interrupts a C-level frame whose `tb_lineno` is `None`, pytest's own
`_getreprcrash` dies formatting it, and mutmut reports "failed to collect stats".
Separately, 3 of 4 tests in `test_gate13_mutmut_config_intact.py` failed inside the
working copy **by construction**, because mutmut copies `setup.cfg` while the G-F
config is swapped in. Those failures would have marked every mutant they covered as
killed. (That file was made context-aware rather than deselected, so it still
asserts the correct scope in whichever tree it runs.)

### Direction of effect

Removing tests can normally only **lower** a mutation score — fewer tests, fewer
kills. The single exception is the spurious textual kills described above, which
this removes. Both effects push the reported number **down or leave it unchanged**.
*This amendment cannot inflate the result*, and that asymmetry is the whole of its
defence.

Deselection is per test **function**, not per file, for the same reason:
`tests/test_tool_surface.py` both scans `*.py` and carries the behavioural tests for
`tool_surface.py` — 287 of G-F's mutants. Dropping the file would have discarded
real coverage and depressed the score for a reason unrelated to the code under test.
An exclusion that removes genuine coverage is no more honest than one that adds fake
kills.

### What this is **not**

It is not "select the tests that should own this behaviour" — the B8 error, where a
behaviour was recorded as uncovered because the nominated subset missed it while
`tests/test_t2_m1_budget_key.py` had covered it all along. Nothing here nominates an
owner for any behaviour, and every behavioural test in the repo remains in the run.

**Measured scale of the exclusion:** the 22 deselections span 13 of 564 test files and
remove **63 of 7226 collected tests — 0.87%**. Verified by collecting the suite with
and without the arguments (`7226 → 93 deselected`, of which 30 are the repo's
pre-existing marker deselects for `slow`/`requires_ollama`/`requires_api_keys`), and by
loading `config/mutmut_gf.cfg` through mutmut's own `_load_config()` to confirm it
parses as 22 separate arguments rather than one.

That last check was not paranoia. The first attempt to measure this reported *zero*
effect, and the config was fine — the shell was passing all 22 flags as a single
argument, because this session's shell is zsh, which does not word-split unquoted
expansions. A control that silently applies nothing looks exactly like a control that
is working.

### How to challenge it

The list is **derived, never hand-written**: `scripts/gf_excluded_tests.py`
regenerates it and `--check` verifies the config still matches, in both directions —
an entry the rule does not derive is a hand-widened exclusion, and an entry the rule
derives but the config lacks means a scanning test is still contaminating the run.
`tests/test_gf_exclusions_derived.py` runs that check in the ordinary suite, bounds
the exclusion to ≤10% of test files, and asserts the biggest module's behavioural
tests survive. Without those, `mutmut_gf.cfg` would be a list of test names somebody
typed, and one more `--deselect` added later to clear the threshold would look
exactly like the other twenty-two.

The rule was wrong twice before it was right, in the same both-directions way as the
CHZ-SS-01 lint earlier in this audit: "any traversal + the word chuzom" swept in 20
files including sandbox tests walking `tmp_path`, and "constructs a `src/chuzom`
path" matched 110+ files because nearly every test builds one for a `sys.path`
insert. Both were caught by inspecting the matches rather than trusting the regex.

### Revision 1a — Rule A2 added, same day, before any score existed

Rule A caught tests that *walk* the source tree. It missed tests that read **one
named source file** and assert on its text. `test_every_success_path_calls_shared_finalizer`
does exactly that:

```python
src = (ROOT / "src" / "chuzom" / "router.py").read_text()
call_sites = len(re.findall(r"await _finalize_successful_route\(", src))
assert call_sites == 5
```

In the working copy it found **9854**, because the file holds every mutant variant. It
passes in the real tree. Rule A was an operationalisation of "inspects source text" that
only covered the tree-walking half.

**Rule A2:** reads the text of a file in `only_mutate` **and** asserts on that text
(`.count(`, `re.findall`, `re.search`, `in src`, `.splitlines(`).

The `only_mutate` restriction is the whole discriminator, and it is not decoration.
mutmut rewrites only those eight files; every other file under `src/chuzom` is copied
verbatim, so reading it yields identical text in both trees and can never produce a
spurious kill. A looser draft that matched anything under `src/chuzom` wrongly caught
`test_cluster5` (reads `rules/chuzom.md`, markdown, never mutated) and
`test_welcome_cli` (reads `cli.py`, not in scope) — 13 real behavioural tests removed to
guard against a risk that does not exist for them.

**Effect: 22 → 25 deselections, 63 → 66 tests, 0.87% → 0.91%.** Three added, all
function-level. The direction-of-effect argument is unchanged and still holds.

Two drafts of this rule were wrong before it was right, both caught by printing the
matches rather than trusting the regex — and one by the guard tests themselves. An
intermediate version collapsed `test_tool_surface.py` into a whole-file exclusion,
which `test_behavioural_tests_for_the_biggest_module_survive_the_exclusion` failed on:
its "module-level scan" detection concatenated every line it had not already attributed
and re-ran the rule, so a `.read_text()` on line 172 joined a `.splitlines(` on line 263
in an unrelated function. Concatenating disjoint regions and pattern-matching the result
measures something that does not exist. Module-level now means outside every top-level
`def`/`class`.

### Not amended

The thresholds (`≥ max(baseline + 0.15, 0.80)`), the conservative scoring rule (§4),
the split and its seal (§2), and the stopping rule (§5) are unchanged.

---

## AMENDMENT 2 — a one-line patch to mutmut, so tests that `chdir` do not abort the run

**Date:** 2026-08-13 · **Requested by:** owner, choosing this over deselecting the
affected tests · **Applies from:** the seventh baseline attempt. **Still no score
existed when it was made** — seven attempts, none reached a tally.

### The defect (upstream, not ours)

`mutmut/__main__.py::record_trampoline_hit` runs on every trampoline hit during the
stats pass:

```python
source_paths = [p.resolve(strict=True) for p in Config.get().source_paths]
if Config.get().max_stack_depth != -1:
    ...   # the ONLY reader of source_paths
```

`source_paths` is `src/chuzom` — **relative**. `resolve(strict=True)` resolves it
against the *current working directory at call time*. Any test that has `chdir`'d away
from the repo root therefore raises:

```
FileNotFoundError: [Errno 2] No such file or directory: 'src'
```

**8 test files (104 tests) `chdir`.** One of them —
`tests/test_setup.py::TestSetupAdd::test_add_writes_to_env`, which is hermetic, using
`tmp_path` and `monkeypatch.chdir` — aborted the entire stats stage, and with it the
whole campaign.

### The patch

Move the computation inside the branch that reads it. That is the whole change.

### Why this cannot affect a score

`max_stack_depth` is `-1` (the default). At `-1` the branch never executes, so
`source_paths` was **computed and discarded** — dead code that could only crash. When
`max_stack_depth` is set to a real depth the value is computed inside the branch and
used exactly as before, so the patch is semantically identical wherever the value is
actually read.

`scripts/gf_mutmut.py::_assert_mutmut_is_patched()` refuses to run if the patch marker
is missing **or if `max_stack_depth` is no longer `-1`** — because the second condition
is the premise of the argument above, not a detail. Verified in both directions: the
guard fires with the marker removed and passes with it restored.

### Why patch rather than exclude

The alternative was deselecting the 8 `chdir`-ing files: 104 tests, 1.44%, on top of
Amendment 1's 66 — about 2.35% of the suite. That is conservative in direction, but it
discards real behavioural coverage for a reason with nothing to do with the code under
test, and every test removed makes the exclusion harder to defend. The patch removes
**zero** tests.

### The cost, stated plainly

This modifies the measuring instrument, which is the thing this protocol is most
careful about elsewhere. Two mitigations: the change is provably inert at
`max_stack_depth == -1`, and the harness refuses to run if either the patch or its
premise goes missing. A `.venv` rebuild silently drops it — without the guard the next
run would die with a `FileNotFoundError` that reads like a repository fault rather than
a missing dependency patch.

Recorded in `run_metadata.json` as `mutmut_amendment2_patch` and
`mutmut_max_stack_depth`.

### Still open after this amendment

The throughput figure in §3 — 14.13 mutations/second, which is what removed sampling
and made "run the full universe" affordable — was measured before any of this was
known and should be treated as **not established**. §3's no-sampling decision must be
re-confirmed against a measured rate from the first successful run.
