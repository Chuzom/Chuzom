# Audit #38 — how many tests are excluded from G-F for a textual reason only

Date: 2026-08-15. Opened by `gf_phase3_c1_failopen.md`, which hit this live: a docstring
naming a gate script excluded the whole file from the qualification run.

## The question

`scripts/gf_excluded_tests.py` rule B is a plain substring match:

    hit = sorted({g for g in _GATE_SCRIPTS if g in segment})

The intent is to exclude tests that INVOKE a gate script as a subprocess — those scan
source text and cannot legitimately kill a mutant. Because it is a substring match, a
test that merely NAMES one in prose is excluded too. An excluded test is deselected from
the run and therefore kills nothing, so if this fires wrongly, **the score is measured
over a smaller suite than intended.**

## Answer: 8 test node ids, in two files

| file | excluded unit | reason given | correct? |
|---|---|---|---|
| `tests/telemetry/test_failopen.py` | **whole file (8 tests)** | B: `lint_fail_open` | **7 wrong, 1 right** |
| `tests/economics/test_calibration_provenance.py` | `test_calibration_coverage_is_reportable` | B: `lint_tool_surface` | **wrong** |
| `tests/routing/test_rules_tool_resolution.py` | 3 tests | B: `lint_tool_surface` | right (see below) |

### `test_failopen.py` — a module docstring costs seven behavioural tests

The mention is prose explaining the division of labour:

> *"The lint (`scripts/lint_fail_open.py`) pins that call sites exist; this pins that the
> mechanism they call actually records…"*

Rule B matches at **module level**, so the classifier excludes the file, not a function —
all eight tests. Seven are ordinary behavioural tests of the fail-open store: records
counted by code, recording never raises when the store is broken, an empty store reads as
zero rather than unknown, an unreadable store reads as unknown rather than zero, partial
corruption still reports what it can, detail is bounded.

Those are exactly the assertions this audit cares about — `test_unreadable_store_is_unknown_not_zero`
is the RED2-02 shape the campaign exists to prevent — and none of them scan source.

**One test in the file IS legitimately excludable**: `test_the_protected_modules_actually_call_it`
does

    total += (src / name).read_text().count("failopen.record(")

over `cost.py`, `router.py`, `execution_ledger.py` — three of the eight mutated modules.
That is caught independently by **rule A2** (reads a mutated source file AND asserts on
its text), so excluding it needs no help from rule B.

Correct outcome for this file: **exclude 1, keep 7.** Actual: exclude 8.

### `test_calibration_provenance.py` — an analogy in a docstring

The mention is a comparison, not a call:

> *"…the identical trap as `tool_surface.unregistered()` checking tier constants against
> `_TIERS`, and `lint_tool_surface.py` checking emitters against emitters."*

The test body calls `calibration_coverage()` and asserts on its numbers. Purely
behavioural. **Wrongly excluded.**

### `test_rules_tool_resolution.py` — correctly excluded, and one of them by luck

Two genuinely invoke the lint (`spec_from_file_location` then `exec_module`, and a
subprocess run). The third, `test_the_lint_scans_markdown_and_json`, does:

    text = (REPO / "scripts" / "lint_tool_surface.py").read_text(encoding="utf-8")
    for suffix in (".md", ".json", ".yaml", ".sh"):
        assert f'"{suffix}"' in text

That reads a source file and asserts on its text — a source-scanning test, correctly
excluded under Amendment 1's intent. But note it is caught by rule **B** (the name
appears) rather than rule **A2**, because A2 only matches the eight *mutated module*
basenames and this file lives in `scripts/`. It is excluded for the right outcome via the
wrong rule; a rule-B fix that ignored prose would need A2 widened, or this test would
silently re-enter the run.

**A first pass classified this one as a false positive.** It is not — the `read_text` plus
assertion is the definition of the class Amendment 1 excludes. Recorded because the
distinction is the whole point of the audit and is easy to get backwards.

## What this means for the 0.5866

Eight test node ids that should be scoring are not. Their absence can only **understate**
the score — an excluded test cannot inflate anything — so the measured 0.5866 is a floor,
not an overstatement. That is the safe direction, and it is the second time this campaign
has found an instrument error biased conservatively (the ⏰ mutants were the first).

It does mean the true score is somewhat higher than measured, by an amount nobody can
state without re-running with those tests included.

## Recommendation — OWNER DECISION, not taken here

Rule B should match an INVOCATION, not a name. Two candidate shapes:

1. require the name to appear alongside an execution signal in the same segment
   (`subprocess`, `exec_module`, `check_output`, `Popen`), or
2. match the path form (`scripts/lint_fail_open.py`) only when it is passed to something
   executable, and widen A2 to cover `.read_text()` on any repo source file rather than
   only the eight mutated modules.

Option 2 is the more honest fix, because it moves `test_the_lint_scans_markdown_and_json`
onto the rule that actually describes why it is excluded.

**Neither is applied.** `scripts/gf_excluded_tests.py` implements Amendment 1, and the
`test_gf_exclusions_derived.py` failure message states the constraint plainly: *"if the
RULE itself needs to change, amend protocol doc 20 first."* Doc 21 records that a third
amendment is a signal to reassess the instrument rather than keep amending. This is
therefore an owner decision, with the cost of inaction now quantified: **7 behavioural
fail-open tests and 1 calibration test are absent from every G-F measurement taken so
far, including the 0.5866 baseline.**
