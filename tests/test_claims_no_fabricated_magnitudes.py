"""Regression / guard: CHZ-AUD-010 — fabricated public claims must not reappear.

The audit found unbacked magnitude claims in the PyPI description and README
("3× longer sessions", "60–90% token savings") and unqualified absolutes
("every prompt flows", "no cloud", "always routes"). This guard scans the
user-facing surfaces the claim-linter previously never checked (pyproject
description + README) and fails if a fabricated/unqualified claim returns. It is
the seed of the G6 claims gate.
"""
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Patterns that must NOT appear unqualified in public marketing surfaces.
FORBIDDEN = [
    re.compile(r"3[×x]\s*longer", re.I),
    re.compile(r"60[–-]?90%", re.I),
    re.compile(r"every prompt flows to the model that fits it", re.I),
    re.compile(r"\bno cloud\b", re.I),
    re.compile(r"zero data leaves your machine", re.I),
]


def _pyproject_description() -> str:
    return tomllib.load(open(ROOT / "pyproject.toml", "rb"))["project"]["description"]


def test_pyproject_description_has_no_fabricated_claims():
    desc = _pyproject_description()
    for pat in FORBIDDEN:
        assert not pat.search(desc), f"fabricated claim in PyPI description: {pat.pattern}"


def test_readme_headline_has_no_fabricated_claims():
    # Scan the first 60 lines (title + hero) where the least-hedged claims lived.
    head = "\n".join((ROOT / "README.md").read_text().splitlines()[:60])
    for pat in FORBIDDEN:
        assert not pat.search(head), f"fabricated claim in README hero: {pat.pattern}"


# RED2-05: the magnitude claim ("60-90%") was still baked into IDE-config
# templates in install_hooks.py, which the two hand-picked scans above never saw.
# The MAGNITUDE claims must not appear ANYWHERE the product writes to a user's
# machine. We scan all shipped source (.py templates + generated .md/.json), not
# just marketing surfaces. (Absolutes like "no cloud" are context-dependent and
# stay scoped to the marketing surfaces above.)
MAGNITUDE_FORBIDDEN = [
    re.compile(r"3[×x]\s*longer", re.I),
    re.compile(r"60[–-]?90\s*%", re.I),
    # RED2-3-02: any unqualified "NN-NNx"/"NNx" cost/speed multiplier claim
    # (e.g. "50–100x less", "100x cheaper"). The guard previously only knew the
    # two specific phrasings above, so "50–100x" shipped into installed rules.
    re.compile(r"\d+\s*[–-]\s*\d+\s*[x×]\b", re.I),
    re.compile(r"\b\d{2,}\s*[x×]\s*(?:less|cheaper|faster|savings?)\b", re.I),
]


def test_no_fabricated_magnitude_claims_anywhere_in_src():
    offenders = []
    # Scan shipped code AND every surface the product ships to a user: src code,
    # bundled rules, and the repo-root skills/ dir (RED2-4-03 — a skill file had a
    # live "50× cheaper" claim the src-only scan missed).
    roots_and_globs = [
        (ROOT / "src" / "chuzom", ("**/*.py", "**/*.md", "**/*.mdc")),
        (ROOT / "skills", ("**/*.md", "**/*.mdc")),
    ]
    for base, globs in roots_and_globs:
        if not base.exists():
            continue
        for g in globs:
            for path in base.rglob(g.replace("**/", "")):
                # skip training-data JSONL and binary
                try:
                    text = path.read_text()
                except OSError:
                    continue
                for pat in MAGNITUDE_FORBIDDEN:
                    if pat.search(text):
                        offenders.append(f"{path.relative_to(ROOT)} :: {pat.pattern}")
    assert not offenders, (
        "fabricated magnitude claim(s) in shipped source (RED2-05/RED2-3-02/RED2-4-03): "
        + "; ".join(offenders)
    )


def test_rules_version_bumped_when_content_changes():
    """RED2-4-02: chuzom.md content changes must bump chuzom-rules-version so
    check_and_update_rules() actually propagates them to installed users."""
    import re as _re
    rules = (ROOT / "src" / "chuzom" / "rules" / "chuzom.md").read_text()
    m = _re.search(r"chuzom-rules-version:\s*(\d+)", rules)
    assert m and int(m.group(1)) >= 7, (
        "rules-version must be >=7 after the iteration-3/4 content reword "
        "(RED2-4-02: a content change without a version bump does not auto-update)"
    )
