# Finding #22 — G4 measures one failure mode and is named for the whole class

Date: 2026-08-13. Raised while writing WP-16 item 1.

---

## G4 was FAILING at HEAD, and I put the failure there

```
G4 test-hygiene: found 35 no-op except handlers in tests/ (baseline 34)
❌ G4 FAIL: new can't-fail test(s) added (35 > 34)
```

The offender was **mine**: `tests/test_env_registry.py:51`, from WP-15.

```python
try:
    tree = ast.parse(path.read_text())
except SyntaxError:
    continue
```

This is the **second** time this session that a CI gate was red at HEAD because I
ran the test suite and not the gates — after three dead imports failed `ruff`.
The recurrence, not the individual miss, is the finding: a green suite is not a
green CI, and I kept treating it as one.

## The skip was hiding a real hole, not just failing a count

The easy fix was raising `TEST_HYGIENE_BASELINE` to 35 — the script explicitly
invites that, and there is precedent (33→34 for an `except OSError: continue`
file-read guard).

**That would have been wrong here.** Silently skipping a file that will not parse
makes the scan cover *less of the codebase than it claims* — and this scan is the
**independent ground truth** the env registry is validated against. Under-reporting
there is the precise failure the file's own header warns about.

So the handler is **gone**, not accounted for. A `src/chuzom` file that cannot be
parsed now fails loudly with a traceback naming it, instead of vanishing from the
denominator. The registry's 8 tests still pass, which proves every file under
`src/chuzom` parses today — the skip was never doing anything except hiding a
hole that did not yet exist.

G4 is back to 34 = baseline, PASS.

## What G4 actually measures

The script is **honest about itself**: its header says it "counts except-handlers
whose entire body is `pass` / `...` / `continue` inside tests/". It was built for
audit pattern D — nine doctor tests wrapped in `try/except Exception: pass`.

The **CI step name** generalised that to *"(no new can't-fail tests)"*. A reader
seeing "G4 PASS" would reasonably conclude that class is covered. It is not.

A swallowed exception is one way a test cannot fail. Three others were found in
this remediation, and G4 structurally cannot see any of them:

| failure mode | where it was found |
|---|---|
| tautological assertion | `assert quota >= 0` on a sum of token counts — **inside Gate 7 itself** |
| assertion on logic re-implemented in the test body | my own first draft of the Gate 7 loss tests |
| a scan that silently returns nothing, making every later assertion vacuous | the reason `test_the_scan_finds_something` exists in three files now |

The CI step is renamed to **"no new SWALLOWED-EXCEPTION tests"**. No behaviour
change; the gate keeps doing exactly what it did. Naming a gate for what it
measures is cheaper than a release note that overstates what was checked, and
this audit exists because of overclaims of precisely that shape.

**Not proposing a new gate.** The criteria are immutable and this is not a
pre-registered one. The 34 grandfathered handlers stay; the ratchet is a
deliberate hold-the-line device, not a claim that the debt is gone.

## Closing #20 — run the gates, not just the suite

Both CI-red-at-HEAD incidents share one cause. The sweep that catches them:

```
uvx ruff@0.16.0 check src/ tests/
.venv/bin/python scripts/lint_tool_surface.py
.venv/bin/python scripts/lint_fail_open.py
.venv/bin/python scripts/verify_criteria_hashes.py
.venv/bin/python scripts/validate_claim_evidence.py
bash scripts/quality_gate_test_hygiene.sh
bash scripts/lint_capability_claims.sh
```

All seven pass at this commit.

And the background-suite wrapper, whose first version reported a **red suite as
exit 0** because the shell returns the *last* command's status and the last
command was a `grep`:

```
pytest ... > f 2>&1; EXIT=$?; grep -ac "^FAILED" f || true; echo "PYTEST_EXIT=$EXIT"; exit $EXIT
```

Never trust a task notification's exit code; open the output file. This is the
same defect class as the verification script that decided catches by
`grep -q "failed"` against uppercase `FAILED` — **twice now, an outcome was
inferred from string-matching output when an exit status was available.**
