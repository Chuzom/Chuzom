# P0 — the test suite read the developer's real session content

Date: 2026-08-14. Found while validating unrelated G-F work; the failure is pre-existing
and was reproduced with the new work removed.

## What happened

A full-suite run failed one test:

    FAILED tests/test_context.py::TestBuildContextMessagesLayer2b
           ::test_session_store_import_failure_is_fail_open

    E  AssertionError: assert 'still works' in
       '[chuzom-session-context]\nROUTED(openai/gpt-4o-mini): is_even(n: int) -> ...
        **Weaknesses**: slower than Flash; avoid for quick lookups.\n[truncated]...'

The test asserts that a context block contains only the string it supplied. The block it
got instead contained **real routed content** — a prompt, a model answer, and profile
prose — none of it produced by the test.

The text was located on disk at
`~/.chuzom/projects/f9b111dafe358d72/session_context_87e1eb21-….jsonl`. That session id is
the Claude Code session that was running the suite. **The suite read the live session
store of the machine it was running on, injected real prompt and model-output text into a
test's messages, and printed it into the run log.**

## Root cause: three sandbox mechanisms, and the module honoured the unused one

| mechanism | used by | `session_store` honoured it |
|---|---|---|
| `CHUZOM_HOME` — canonical, what `paths.is_isolated()` reports on | 6 test files, 8 src sites | **no** |
| monkeypatching `pathlib.Path.home` — this repo's conftest (`:315`, `:329`) | 88 test files, 153 src sites | **no** |
| the `HOME` environment variable | nothing in this suite | yes |

    def _state_dir() -> Path:
        """Resolve ``~/.chuzom`` at call time (so monkeypatched HOME works)."""
        return Path(os.path.expanduser("~")) / ".chuzom"

`os.path.expanduser("~")` reads the `HOME` env var. Replacing the `pathlib.Path.home`
*method* — what conftest does — does not change it. The docstring is true of a mechanism
nothing in this suite uses.

Measured, not inferred:

    CHUZOM_HOME=/tmp/isolated-sandbox
      is_isolated()               True
      paths.chuzom_home()         /tmp/isolated-sandbox
      session_store._state_dir()  /Users/yaliandrona/.chuzom     <- outside the sandbox

    with patch("pathlib.Path.home", return_value=/tmp/fake-home)
      Path.home()                 /tmp/fake-home
      session_store._state_dir()  /Users/yaliandrona/.chuzom     <- outside the sandbox

    HOME=/tmp/fake-home
      session_store._state_dir()  /tmp/fake-home/.chuzom          <- the only one honoured

## Why this is more than a flaky test

`is_isolated()` exists for exactly this, in its own docstring: *"Exposed so a destructive
test can assert its sandbox took effect instead of assuming it did — the assumption is
what caused the incident."* It returns `True` while this module reads and writes outside
that sandbox. **A guard reporting clean while blind** is the recurring defect class of
this audit — eleven prior instances — and here it guarded the store holding user prompt
text.

Two consequences beyond the red:

1. **Privacy.** Real prompts and model outputs entered a test assertion message and a log
   file. On a developer machine that log is local; in any setting where CI output is
   shared, it is not.
2. **Deployment.** Any host relocating state with `CHUZOM_HOME` — a sandbox, a CI runner,
   a multi-tenant deployment — had session context written to and read from the real home
   regardless of the setting.

This is the same family as finding #30 (the suite writing synthetic rows into the real
`usage.db`) but in the **read** direction, and against content rather than counters.

## The fix

`_state_dir()` now delegates to `paths.chuzom_home()`, so there is one answer to "where
does state live". That honours `CHUZOM_HOME` **and**, through `Path.home()`, the
`pathlib.Path.home` patch — both mechanisms the suite actually uses. Nothing that
previously worked stops working: the `HOME` env var still resolves through `Path.home()`.

`tests/test_p0_session_store_isolation.py` — 6 tests. Red proven by reverting the fix:

    with the fix    rc=0  failures=0
    fix REVERTED    rc=1  failures=6   (all six, for the defect)
    fix RESTORED    rc=0  failures=0

One of the six asserts that `_state_dir()` **agrees with** `chuzom_home()` rather than
checking each separately. Divergence between two implementations of the same question was
the defect; asserting agreement is what makes a future divergence fail here.

### A mistake in the regression test, worth recording

The leak check first searched the whole real store for a canary string. It failed — but
not on the defect. Chuzom correctly records the developer's tool calls, so *editing the
test file* wrote the canary's name into a real session log, and the test failed on the
product working as designed. It now keys on a per-run UUID session id, which can only
appear in a file the test itself caused to be created.

A test artefact (`session_context_iso-sess.jsonl`, one line) that the pre-fix red run
leaked into the real store was inspected and removed. No user data was touched.

## Scope NOT addressed — owner decision

**153 sites across `src/chuzom/` resolve `~/.chuzom` directly and ignore `CHUZOM_HOME`;
8 use the canonical helper. Three modules import `chuzom.paths` at all.**

Only the one site with a demonstrated live failure was fixed. The rest are unproven, and
changing 153 state-root resolutions without a failing case for each is not a bug fix — it
is a refactor of where every user's data lives, and it belongs to the owner.

Two things worth weighing:

* 44 of the 153 are in `hooks/`, which run as separate processes and may deliberately
  need the real home regardless of an ambient env var.
* The 88 test files patching `Path.home()` are genuinely isolated for those 153 sites,
  because they are `Path.home()`-based. The gap is specifically between `CHUZOM_HOME` —
  which `is_isolated()` blesses — and everything else.

**Recommendation:** treat `is_isolated()` as the claim to make true. Either route the
remaining sites through `paths`, or narrow what `is_isolated()` asserts so it stops
certifying a sandbox that mostly does not exist. The present state, where it returns True
for state it does not govern, is the worst of the three.
