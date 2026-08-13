"""Gate 13's mutmut scope must survive every G-F run.

`scripts/gf_mutmut.py` swaps `config/mutmut_gf.cfg` into `setup.cfg` for the
duration of one mutation run and restores the original afterwards. If a run is
killed between those two steps — Ctrl-C, an OOM, a laptop lid — `setup.cfg` is
left holding the **G-F** scope while claiming to be Gate 13's.

Nothing else would notice. mutmut would keep running, over the wrong eight files,
and report a perfectly well-formed score. That is the exact failure shape this
audit keeps finding: a wrong measurement that looks like a right one.

These assertions run in the ordinary suite, so a stranded swap is caught on the
next test run rather than the next release.

WHY THIS FILE EXISTS RATHER THAN TRUSTING THE `finally`
--------------------------------------------------------
`gf_mutmut.py` restores in a `finally` and verifies the sha256 matches. That
covers the ordinary failure paths. It does **not** cover the process being killed
outright, which is precisely when a swap is most likely to strand. A guard that
depends on the guarded code running to completion is not a guard.
"""

from __future__ import annotations

import configparser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SETUP_CFG = _ROOT / "setup.cfg"

#: The Gate-13 campaign's scope. Committed here as an INDEPENDENT declaration —
#: reading it out of setup.cfg and comparing it to setup.cfg would pass no matter
#: what the file contained, which is the self-validating shape found four times
#: in this audit already.
_GATE13_ONLY_MUTATE = {
    "src/chuzom/execution_ledger.py",
    "src/chuzom/execution_signal.py",
    "src/chuzom/operational_signal.py",
    "src/chuzom/context_signal.py",
    "src/chuzom/gates.py",
    "bench/savings.py",
}


def _only_mutate() -> set[str]:
    cfg = configparser.ConfigParser()
    cfg.read(_SETUP_CFG)
    raw = cfg.get("mutmut", "only_mutate", fallback="")
    return {line.strip() for line in raw.splitlines() if line.strip()}


def test_setup_cfg_still_holds_gate_13_scope():
    """The load-bearing assertion: a stranded G-F swap fails here."""
    actual = _only_mutate()
    assert actual == _GATE13_ONLY_MUTATE, (
        "setup.cfg's [mutmut] scope is not Gate 13's.\n"
        f"  missing: {sorted(_GATE13_ONLY_MUTATE - actual)}\n"
        f"  unexpected: {sorted(actual - _GATE13_ONLY_MUTATE)}\n"
        "If the unexpected entries are G-F's eight modules, a gf_mutmut.py run "
        "was killed mid-swap. Restore setup.cfg from git."
    )


def test_gate_13_keeps_its_explicit_test_selection():
    """Its per-module test list is part of the campaign's evidence. G-F
    deliberately omits one; losing Gate 13's would silently widen its runs and
    change its score without changing its scope."""
    cfg = configparser.ConfigParser()
    cfg.read(_SETUP_CFG)
    sel = cfg.get("mutmut", "pytest_add_cli_args_test_selection", fallback="")
    assert "tests/test_gates_mutation_coverage.py" in sel, (
        "Gate 13's explicit test selection is gone from setup.cfg"
    )


def test_pyproject_does_not_hijack_mutmut_config():
    """mutmut 3.6 prefers pyproject.toml [tool.mutmut] and IGNORES setup.cfg
    entirely when it is present.

    Adding that section — the obvious way to give G-F its own config — would
    silently disable Gate 13's scope rather than sitting beside it. This asserts
    nobody has, so the swap in gf_mutmut.py still means what it says.
    """
    assert "[tool.mutmut]" not in (_ROOT / "pyproject.toml").read_text(), (
        "pyproject.toml has a [tool.mutmut] section; mutmut will ignore "
        "setup.cfg entirely and BOTH the Gate-13 scope and the G-F swap become "
        "no-ops that still produce a score"
    )


def test_the_gf_config_exists_and_targets_a_different_scope():
    """Guards the guard: if config/mutmut_gf.cfg vanished or drifted to Gate
    13's scope, the tests above would pass while G-F measured nothing new."""
    gf = _ROOT / "config" / "mutmut_gf.cfg"
    assert gf.exists(), "config/mutmut_gf.cfg is missing"

    cfg = configparser.ConfigParser()
    cfg.read(gf)
    gf_scope = {
        line.strip()
        for line in cfg.get("mutmut", "only_mutate", fallback="").splitlines()
        if line.strip()
    }
    assert len(gf_scope) == 8, f"expected G-F's eight modules, got {len(gf_scope)}"
    assert gf_scope != _GATE13_ONLY_MUTATE, "the G-F config duplicates Gate 13's scope"
    # execution_ledger.py is the single legitimate overlap between the campaigns.
    assert gf_scope & _GATE13_ONLY_MUTATE == {"src/chuzom/execution_ledger.py"}
