# WP-11 — `doctor` tells the truth

Date: 2026-08-12. Findings RED4-02, RED1-23.

---

## Criterion 1 — with a real regression injected, `doctor` exits non-zero and names the defect

**Baseline (RED), measured before any change.** Injected a genuine tool-surface
regression in a detached worktree — `CORE_TOOLS`'s `"llm_query"` replaced with
`"llm_bogus_xyz"`, a single-site change verified to alter behaviour — then ran
`chuzom doctor` and diffed against a healthy run:

```
exit = 0
diff healthy vs broken:
  73c73
  <   ✓ last_classification_*.json fresh (5s, …)
  >   ✓ last_classification_*.json fresh (22s, …)
```

The only difference was a freshness timestamp. Functionally byte-for-byte
identical, exactly as RED4-02 described.

**After.**

```
healthy tree : EXIT=0   ✓ All doctor checks passed (see NOT CHECKED above).
broken  tree : EXIT=1   ✗ tier offers 1 tool(s) nothing implements: llm_bogus_xyz
                        • tool surface names unimplemented tool(s): llm_bogus_xyz
```

### Why doctor could not see it

`doctor` relied on `tool_surface.unregistered()`, which looks like validation:

```
registered_tools(slim) -> _TIERS[slim] -> CORE_TOOLS / ROUTING_TOOLS / ...
unregistered(names)    -> [n for n in names if resolve(n).name not in reg]
```

It checks the tier constants against `_TIERS`, which **is** the tier constants.
Rename a tool inside `CORE_TOOLS` and the "registered" set contains the new name,
so the check reports clean. Self-consistency wearing a validation check's clothes.

Fixed by promoting ground truth into production code:
`tool_surface.implemented_tools()` reads the tool coroutines actually defined
under `chuzom/tools/` by AST, and `phantom_tools()` reports tier entries nothing
implements. Stdlib-only, so the module's deliberately dependency-free contract
(hooks load it by path) still holds. Unknown-safe: if ground truth cannot be
read it returns `[]` rather than reporting every tool as phantom — a check that
screams on its own failure gets muted.

`doctor` checks **all three tiers**, not just the active one. A defect in a tier
this machine does not run still ships to everyone who does, and doctor output is
what people paste into bug reports.

## The exit code was thrown away — across seventeen commands

`doctor` detected and printed the defect while still exiting 0. The cause was not
in doctor: `cli.py` carried two dispatch styles in one function.

```
sys.exit(cmd_stats(args[1:]))     # later branches — propagate
cmd_doctor(args[1:])              # 18 earlier branches — discarded
```

Seventeen of the eighteen are annotated `-> int`. So until now:

| Command | On failure |
|---|---|
| `chuzom install` | exits 0 |
| `chuzom uninstall` | exits 0 |
| `chuzom update` | exits 0 |
| `chuzom test` | exits 0 |
| `chuzom config` | exits 0 |
| `chuzom doctor` | exits 0 |
| …11 more | exits 0 |

`chuzom install && echo ok` printed `ok` on a failed install. All seventeen fixed
after confirming the dispatch chain is terminal. `cmd_okf` returns `None` and was
left alone rather than have its contract changed here.

This is the session's recurring shape at its widest: a signal that exists, is
computed correctly, and is discarded before anyone can act on it.

## Criterion 2 — `doctor` states what it did NOT check

A green doctor implies "your install is fine". It checks roughly a dozen things.
The closing line was `✓ All checks passed. Chuzom is healthy.` — which is what
let a passing run be read as far more evidence than it measured. It now reads
`✓ All doctor checks passed (see NOT CHECKED above)`, above an explicit list:

- live routing accuracy — whether hints actually reach a cheaper model
- quality of routed answers — no judge runs here
- cost/savings correctness — figures are reported, not verified
- provider availability under load, rate limits, quota exhaustion
- hook behaviour on prompts other than the synthetic probe

A test asserts the section names concrete, actionable paths rather than a vague
disclaimer, because a vague one looks like disclosure while telling the operator
nothing.

## Criterion 3 — `trace_northstar.py` referenced by CI

It was referenced by a CHANGELOG line and nothing else — not by CI, not by
doctor. A guard nobody invokes is documentation.

**It needed hardening before it was worth invoking.** Run against the same
injected regression, it reported:

```
CHUZOM_SLIM=core   server registers 3 tools      (was 4)
  ✓ what is the capital of France   hint→ llm_code   registered=True
TRACE CLEAN — every emitted hint names a tool the server registers
exit = 0
```

`llm_bogus_xyz` cannot be registered, so the tier silently shrank 4→3 and the
fallback chain degraded every `llm_query` hint to `llm_code`. Every hint still
named a registered tool, so the invariant held while **query prompts were being
routed to the code tool**. Consistency preserved, correctness lost.

"Every hint names a registered tool" is necessary, not sufficient. The trace now
also asserts the reverse — every tool a tier DECLARES must actually be
registered — and catches it:

```
✗ tier declares 4 tools but the server registered 3; missing: llm_bogus_xyz
exit = 1
```

Wired into `ci.yml`'s lint job. Wiring it in unhardened would have added a green
checkmark that proved nothing, which is worse than the gap it was closing.

## Note for the re-audit

Three separate guards in this work package were **present, running, and green**
while blind to the defect they existed to catch: `unregistered()`,
`lint_tool_surface.py`, and `trace_northstar.py`. None was missing; each was
measuring an invariant adjacent to the one that mattered. A guard's existence,
and even its passing, is not evidence that the thing it names is checked.
