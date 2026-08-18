"""The Stop hook's output must be tunable — it fires every turn, not at session end.

WHY THIS EXISTS (CHZ-STOP-01)
=============================

`session-end.py` is registered as a **`Stop`** hook, and `Stop` fires after every
agent response. The filename says session-end; the cadence is per-turn. So the
heaviest output this project produces was printing after every single response,
with no toggle — the only workaround being to unregister the hook, which loses
the information entirely rather than quieting it.

The defect is the MISMATCH, not the block's size. At session-end cadence a full
boxed summary is proportionate. At per-turn cadence it is not.

    full       the boxed summary, unchanged
    condensed  one line, and only when something happened   (default)
    disabled   nothing; `chuzom summary` on demand

WHY condensed IS THE DEFAULT, decided rather than adopted: a default should match
the frequency of the event that triggers it. `full` is one env var away and
byte-identical for anyone who preferred it, so the cost of being wrong here is a
single setting; the cost of leaving it as-is is every user, every turn.

Two properties that are easy to get wrong and are asserted below:

  * condensed emits NOTHING when there is nothing to report. A per-turn line
    saying "no activity" is the same defect one size smaller.
  * an unrecognised value falls back rather than raising. This code runs after
    every turn; a hook that fails closed on a misspelled env var would break the
    session it exists to summarise.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / "src" / "chuzom" / "hooks" / "session-end.py"

_BOXED = (
    "  " + "═" * 40 + "\n"
    "  ⚡ Chuzom session summary\n"
    "  12 routes\n"
    "    \x1b[32m\x1b[1m$412.88\x1b[0m  lifetime    \x1b[37m$3.41\x1b[0m  today\n"
    "  " + "═" * 40
)
_EMPTY = "  " + "═" * 40 + "\n  No session activity detected\n  " + "═" * 40


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("_se", _HOOK)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_se"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_is_condensed(hook, monkeypatch):
    """Unset must not mean `full` — that is the state being fixed."""
    monkeypatch.delenv(hook._STOP_HOOK_ENV, raising=False)
    assert hook._stop_hook_mode() == "condensed"


@pytest.mark.parametrize("mode", ["full", "condensed", "disabled"])
def test_each_mode_resolves(hook, monkeypatch, mode: str):
    monkeypatch.setenv(hook._STOP_HOOK_ENV, mode)
    assert hook._stop_hook_mode() == mode


@pytest.mark.parametrize("value", ["FULL", " Disabled ", "CONDENSED"])
def test_modes_are_case_and_space_insensitive(hook, monkeypatch, value: str):
    monkeypatch.setenv(hook._STOP_HOOK_ENV, value)
    assert hook._stop_hook_mode() == value.strip().lower()


@pytest.mark.parametrize("value", ["quiet", "off", "1", "yes", "", "ful"])
def test_unknown_values_fall_back_instead_of_raising(hook, monkeypatch, value: str):
    """A hook that dies on a typo breaks the session it only summarises."""
    monkeypatch.setenv(hook._STOP_HOOK_ENV, value)
    assert hook._stop_hook_mode() == "condensed"


def test_condensed_reports_both_scopes(hook):
    """Today AND lifetime, each labelled.

    A single unlabelled figure is the bug this replaced: the first version took
    whichever `$x.xx` appeared first, so a per-turn line reading "saved $412.88"
    silently meant LIFETIME and would be read as this session by anyone glancing
    at it. Worse than printing nothing.
    """
    line = hook._condense(_BOXED)
    assert "12 routed" in line
    assert "today $3.41" in line, "today's figure missing or unlabelled"
    assert "lifetime $412.88" in line, "lifetime figure missing or unlabelled"
    assert "\n" not in line, "condensed must be ONE line — it prints every turn"


def test_it_survives_the_ansi_codes_the_renderer_emits(hook):
    """The real box is coloured. A regex that only matches plain text would
    silently find nothing and report an empty line every turn — passing tests
    against synthetic input while doing nothing in production."""
    assert "\x1b[" in _BOXED, "fixture must contain ANSI, or this proves nothing"
    assert "$3.41" in hook._condense(_BOXED)


def test_a_lone_figure_is_still_labelled(hook):
    """Never emit a bare number. If only one scope is available the reader must
    still know which one it is."""
    only_life = hook._condense("    $99.00  lifetime")
    assert "lifetime $99.00" in only_life


def test_condensed_says_nothing_when_there_is_nothing(hook):
    """A per-turn 'no activity' line is the same defect, one size smaller."""
    assert hook._condense(_EMPTY) == ""


def test_condensed_is_derived_from_the_rendered_summary(hook):
    """Figures are extracted, not recomputed, so the two modes cannot disagree.

    If condensed ever recalculated spend independently, it could report a
    different number than `full` for the same session — a reporting bug that
    would be very hard to notice and impossible to trust.
    """
    altered = _BOXED.replace("$3.41", "$9.99").replace("12 routes", "7 routes")
    line = hook._condense(altered)
    assert "today $9.99" in line and "7 routed" in line
    assert "3.41" not in line
