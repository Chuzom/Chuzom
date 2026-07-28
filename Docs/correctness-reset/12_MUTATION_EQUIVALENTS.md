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

## Still to register (open Gate-13 work)

- `src/chuzom/router.py` — the reset's new routing code (exhaustion floor, block
  filter, metered mid-tier) is not yet mutation-run; needs an async-harness test
  selection, then its non-equivalent mutants killed and any equivalents added here.
- The previously-scoped hermetic modules (`execution_ledger`, `execution_signal`,
  `operational_signal`, `context_signal`, `bench/savings`) were covered in the
  earlier Phase-7 pass; their equivalent classes are described in
  `03_RELEASE_GATES.md` Gate 13 and should be folded into this registry when Gate
  13 is finalized.

Gate 13 flips to **PASS** once `gates.py` (done) **and** `router.py` are both closed
to the "non-equivalent killed + equivalents registered" bar.
