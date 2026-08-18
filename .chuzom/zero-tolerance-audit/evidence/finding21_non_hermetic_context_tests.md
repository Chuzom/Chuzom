# Finding #21 — a test whose own fixture documents the hazard it does not apply

Date: 2026-08-12. Found while validating finding #12.

---

## What happened

`tests/test_context.py::TestBuildContextMessages::test_combined_context_order`
failed a full-suite run:

```
content.index("Additional context")  ->  ValueError: substring not found
```

| run | tree | result |
|---|---|---|
| 1 | mine (with #12 changes) | **FAILED** |
| 2 | clean HEAD, detached worktree, identical flags | passed |
| 3 | mine, identical flags | passed |
| — | that test alone, and the whole file alone, on both trees | pass |

**1 fail / 1 pass on the same tree.** Flaky and state-dependent — not a
regression from the calibration change. `~/.chuzom` changed between runs 1 and 3
(two MCP `llm()` calls and the probe scripts wrote there).

## The proven defect

`tests/test_context.py:194` defines `reset_session_buffer` as a plain
`@pytest.fixture` — **not autouse**. It does two things: resets the global session
buffer, and repoints `HOME` at a temp dir. Its own docstring states the hazard:

> Without isolating HOME the test read the developer's LIVE session accumulator
> (populated by the active chuzom hooks) and non-deterministically saw context
> where the test expects none.

Members at lines 211/218/232 request it. `test_combined_context_order` (247) and
`test_respects_token_budget` (270) did not.

**Instrumented** (`scratchpad/probe_context.py`): live `HOME` yields **2854**
characters of context where an isolated `HOME` yields **159** — an 18× leak. The
non-hermeticity is measured, not inferred.

So this is a file that documents a hazard in its own fixture and then leaves two
of its members exposed to it.

## What it cost, and two hypotheses I had to abandon

Resolving one false red took three full-suite runs, a control worktree and two
instrumented probes. Both leading hypotheses died on measurement:

1. **HOME leakage alone.** Ruled out: the probe showed `extra=True` with *both*
   real and isolated HOME. The leak is real; it is not sufficient.
2. **Budget truncation dropping the caller's own context.** Ruled out: swept the
   buffer from 1×10 to 50×10000 characters; content caps at 2395 and
   `extra=True` at **every** level. Caller context is never the thing dropped —
   which is also a small piece of good news about the product.
3. **Downgraded, not confirmed:** that `test_calibration_provenance.py::_load_hook()`
   `exec_module`-ing `auto-route.py` three times (and `tests/economics/` sorting
   before `tests/test_context.py`) polluted the durable accumulator. Run 3 passing
   killed it — a deterministic pollution mechanism would have failed run 3 too.

**The specific polluter is still unidentified.** What is established is that the
test's outcome depends on live machine state, and that removing that dependency
removes the flake. Recording the open end rather than closing it with the
best-sounding story.

A false red is not free. Had it been trusted it would have sent someone hunting a
regression in the calibration change that did not exist.

## The fix, and why it is a guard rather than a patch

The obvious fix — mark the fixture `autouse=True` — would silently correct
today's two tests and leave the next author free to add a third non-hermetic test
in another class. So `tests/test_context_hermetic.py` asserts the property
directly: every `test_*` in `TestBuildContextMessages` requests the isolation
fixture. RED before the fix (naming both offenders by name), GREEN after.

Three assertions, each earning its place:

- **`test_the_guard_finds_the_class_and_its_tests`** — guards the guard. If the
  AST parse returns nothing (class renamed, file moved) every other assertion
  passes vacuously. That is the failure mode that let a broken probe report
  "0/6 reproductions" earlier in this audit while measuring nothing.
- **`test_every_context_building_test_isolates_home`** — the criterion.
- **`test_the_fixture_still_isolates_home`** — the fixture's value is the `HOME`
  repoint, not its name. Drop the `monkeypatch.setenv` and keep the buffer reset,
  and every test still "requests the fixture" while the hazard returns. A guard
  that passes on a name after the behaviour is gone is the same defect class as
  `unregistered()` checking tier constants against `_TIERS`.

## Relation to G4

The repo already runs **G4, a "test-hygiene ratchet (no new can't-fail tests)"**.
It catches tests that *cannot fail*. It does not catch tests that can fail
*spuriously* — the other half of the same problem, and arguably the more
expensive one: a can't-fail test costs you a defect you never see, while a
flaky test costs an investigation cycle every time it fires and trains people to
re-run the suite instead of reading the failure.

Not proposing a new gate — the criteria are immutable and this is not a
pre-registered one. Recording it because the re-audit should not read "G4 passes"
as "test hygiene is covered".
