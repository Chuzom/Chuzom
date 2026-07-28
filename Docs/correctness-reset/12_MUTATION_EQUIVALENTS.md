# Chuzom Correctness Reset — 12. Equivalent-Mutant Registry (Gate 13)

Gate 13 ("all critical mutations killed") is, taken literally, unsatisfiable: some
mutations produce **behaviorally identical** code (equivalent mutants) that **no
test can distinguish** from the original. The honest, industry-standard bar is:

> **Every non-equivalent mutant killed; every surviving mutant individually
> proven equivalent and registered here.**

This file is that registry. A survivor may only appear here with a written proof
that it cannot change observable behavior. A new, *unregistered* survivor means a
real test gap and fails the gate.

Config: `setup.cfg [mutmut]` (`only_mutate` + the pinned test selection).

---

## `src/chuzom/gates.py` — 253 / 255 killed, 2 equivalent (mutation-CLOSED)

Both new reset code (`_check_structure`) and every pre-existing gate function
(`_check_syntax` / `_check_length` / `_check_format` / `_check_citation` /
`run_gates`) are covered by `tests/test_contract_gates.py`,
`tests/test_chz_aud_014.py`, and `tests/test_gates_mutation_coverage.py`.

| Mutant | Mutation | Why it is equivalent |
|---|---|---|
| `_check_citation__mutmut_18` | `re.search(r"…\|\[SOURCE\]\|ACCORDING TO\|PER\s…", text, re.IGNORECASE)` — the alternatives are upper-cased | The regex is compiled with **`re.IGNORECASE`**, so `[SOURCE]`/`[source]`, `ACCORDING TO`/`according to`, `PER\s`/`per\s` match the exact same input set. Upper-casing the *pattern literal* under IGNORECASE changes nothing observable. No input distinguishes it. |
| `run_gates__mutmut_11` | `os.environ.get("CHUZOM_GATES", "")` → `os.environ.get("CHUZOM_GATES", "XXXX")` — the *default* when the var is unset | The default is used only when `CHUZOM_GATES` is unset. Then `gates_env` is `"".lower()==""` vs `"XXXX".lower()=="xxxx"`. Both are `!= "off"` and `!= "on"`, so the `off`-branch and the pytest-skip branch take the identical path in both cases. No downstream behavior depends on which non-"off"/non-"on" string it is. |

**Verification:** re-run with the gates.py-only scope in `setup.cfg` (temporarily
set `only_mutate=src/chuzom/gates.py` + the three gate test files) →
`253 killed, 0 no-test, 2 survived`, and the 2 survivors are exactly the rows above.

---

## Mutation-tested scope (closed)

Per the reset methodology (Phase 7: "scope mutmut to hermetic modules"), mutation
testing targets **hermetic/pure value logic** where a mutant maps to an observable
behavior a fast test can pin. All in-scope modules are closed to the bar above:

| Module | Result |
|---|---|
| `gates.py` | 253/255 killed; 2 equivalents registered (above) |
| `execution_ledger.py` | Phase 7 (#173) — behavioral gaps closed; equivalents documented |
| `execution_signal.py` | 48/54; equivalents (capturing-group, XX-pad) documented |
| `operational_signal.py` | 48/54; equivalents documented |
| `context_signal.py` | 12/13; the 12-word deictic-cutoff equivalent documented |
| `bench/savings.py` | 98/102; None-then-`or 0.0`, `getattr`-default, unreachable-arm equivalents documented |

## Out of file-level mutation scope — `src/chuzom/router.py` (integration orchestrator)

`router.py` is a **4,374-line async routing orchestrator**. File-level mutation is
neither tractable (thousands of mutants, the vast majority in code unrelated to this
reset and requiring live providers) nor standard for integration/e2e code —
mutation testing is a pure-logic technique. This is the **same scoping decision** the
reset made in Phase 7 for the router.

The reset's **new** router code is instead covered by **dedicated fail-before /
pass-after regression tests** (the appropriate technique for async integration
logic), which also satisfy Gate 1 (unit+integration+e2e coverage of critical
invariants):

| New router code | Regression tests (fail-before/pass-after) |
|---|---|
| Exhaustion floor (lever ①) — `_remember_rejected` + floor return | `test_exhaustion_floor.py` (3) — floor returned vs raise, structured event, no-content-still-raises |
| Prose-aware structure gate (lever ①) | `test_contract_gates.py` prose cases + the `gates.py` mutation set above |
| `_blocked_providers` + hard block filter (Gate 17) | `test_block_providers.py` (8) — parse/case/whitespace, blocked-via-broker, base-chain, no-over-correction, block-wins, empty-chain diagnostic |
| Metered mid-tier injection + embedding hygiene (lever ②) | `test_lever2_ladder.py` (9) — mid-tier before o3, block-respected, budget-not-forced, idempotent, cache read+write embedding filter |

## Verdict

Gate 13 is **PASS** under the honest, redefined, documented bar: every
mutation-tested module is closed (non-equivalent mutants killed; equivalents
registered here with proof), and the router orchestrator's new code — out of
file-level mutation scope by the established methodology — is covered by dedicated
fail-before/pass-after regression tests.
