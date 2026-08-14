# G-F Phase 2 — what the 614 TRAIN survivors are missing

Date: 2026-08-14. Protocol: `20_GF_QUALIFICATION_PROTOCOL.md` §5. Plan: doc 21 Step 2.
Input: the attempt-12 baseline (`1f104ba`), TRAIN only.

**Validation and holdout were not inspected.** Choosing what to fix by looking at
validation converts it into a second training set and destroys the only check on
overfitting that this campaign has.

---

## The instrument, validated before use

Outcomes come from `mutmut_stdout.txt` — one line per mutant — not from `mutmut results`,
whose scope Phase 1 could not account for. The parse is trusted only because it
independently reproduces both committed figures: TRAIN 904/1518 and VALIDATION 261/468,
with zero names missing a line. A classifier that silently drops mutants looks exactly
like one that works.

Each survivor's actual mutation is recovered by diffing `x_f__mutmut_N` against
`x_f__mutmut_orig` in mutmut's own working copy — read out of the artefact that ran,
rather than inferred from what a mutation tool "would" do.

**The classifier was wrong twice and both fixes changed the answer**, which is the reason
to say so rather than present the final table as if it fell out first time:

1. `<=` → `<` was landing in `unclassified` because the operator rules tested membership
   (`"<=" in text`) instead of counting longest-match-first. Boundary flips — the
   off-by-one class — were invisible. 95 unclassified became 37.
2. `x is None` → `x is not None` was unclassifiable because `is not` *contains* ` is `, so
   both sides counted an `is` and no removal/addition pair could form. Null-check
   inversion was invisible.

Final: 606 of 614 classified (98.7%). The 8 remaining are enumerated in §6 rather than
absorbed into a bucket.

---

## 1. The finding that reframes the work

**All 614 survivors live in 82 functions. Twenty of those functions hold 411 of them.**

| functions covered | survivors reachable | TRAIN score if all were killed |
|---|---|---|
| top 10 | 283 (46%) | 0.7819 |
| **top 20** | **411 (67%)** | **0.8663** |
| top 30 | 481 (78%) | 0.9124 |
| top 40 | 528 (86%) | 0.9433 |
| all 82 | 614 (100%) | 1.0000 |

Doc 21 framed the remaining work as "~425 mutants". That framing is misleading: it is
**~20 functions that need real tests**, and the mutants are how you tell when a function
has them. Twelve of the 82 functions hold exactly one survivor each and are noise.

The right-hand column is an **upper bound, not a forecast** — it assumes every survivor in
a covered function dies, and §5 lists reasons some cannot. At a more realistic 70% kill
rate, the top 30 functions still reach 904 + 0.7×481 = 1241/1518 = **0.818**. The floor is
reachable from this structure. That is a claim about arithmetic, not about difficulty.

---

## 2. The primary axis: outcome, because the three need different work

| outcome | n | what it means | what closes it |
|---|---|---|---|
| 🙁 survived | 450 | tests execute the line and do not notice the change | strengthen the assertion |
| 🫥 no-coverage | 107 | no test executes the line at all | write any test |
| ⏰ timeout | 57 | the mutant hangs | **see §4 — open** |

The no-coverage set is nine functions, and six of them are 100% uncovered:

| n | function |
|---|---|
| 38 | `cost.fire_budget_alert` |
| 20 | `cost.refresh_baseline_pricing_from_api` |
| 18 | `budget.format_budget_summary` |
| 10 | `execution_ledger.get_turn_accounting` |
| 6 | `cost._restore_claim` |
| 6 | `tool_surface.door_name` |
| 3 each | `budget.invalidate_cache`, `router._auth_error_hint`, `tool_surface.resolve_name` |

`get_turn_accounting` is worth naming on its own: it is the per-turn money accounting
entry point, and **no test in the suite executes it.**

---

## 3. Classes, by what a test would have to assert

### C1 — fail-open codes are never asserted (40 mutants, 11 codes, 11 functions)

Every `failopen.record("CHZ-FO-…", exc)` call site survives mutation of its code string,
its argument, and its default. Eleven distinct codes:

    CHZ-FO-COST-BUDGET-ALERT        CHZ-FO-ROUTER-BASELINE-ESTIMATE
    CHZ-FO-COST-COVERAGE-COUNTS     CHZ-FO-ROUTER-DESKTOP-NOTIFY
    CHZ-FO-COST-IDENTITY            CHZ-FO-ROUTER-LEDGER-EMIT
    CHZ-FO-COST-PRICING-REFRESH     CHZ-FO-ROUTER-LEDGER-TERMINAL
    CHZ-FO-LEDGER-HOST-RATES        CHZ-FO-ROUTER-PRICE-TABLE-VERSION
                                    CHZ-FO-ROUTER-PROVIDER-PARSE

One root cause: **no test drives any of these error paths and asserts which code was
recorded.** A mutant can swap the code, lower-case it, or pass `None`, and nothing objects.

This is the same hole as open finding **#32** (`lint_fail_open` cannot detect a fail-open
that logs), arrived at from the opposite direction. #32 says the *linter* cannot see these
paths; C1 says the *tests* do not either. WP-13 was marked complete using that linter as
its instrument, so its clean result covers less than the title implies — and now there is
a second, independent measurement saying so.

Highest-value class in the set: behavioural, auditable, and it closes a known gap.

### C2 — env-var overrides are never exercised (10 mutants)

`os.environ.get("CHUZOM_GEMINI_BASELINE", "")` → `None`, and siblings for
`CHUZOM_CODEX_BASELINE`. The override is documented behaviour; no test sets the variable
and asserts it takes effect. Cheap to close.

### C3 — dict `.get()` defaults removed (12 mutants)

`_TIER_FLOOR.get(tier, "llm_query")` → `.get(tier, )`; `MODEL_COST_PER_1K.get(model, 0)`
→ `.get(model, )`. Removing the default turns a graceful fallback into a `TypeError`. The
mutants survive because **no test passes an unknown key** — no unknown tier, no unmapped
model. The `calc_savings` instance is on a money path.

### C4 — ordering arguments (13 mutants)

`sorted(DEPRECATED_TOOLS, key=len, reverse=True)` → `key=None`, or `reverse` dropped.
Longest-first matching exists so a short deprecated name cannot shadow a longer one; no
test has two names where one is a prefix of the other, so the ordering is free to change.

### C5 — SQL text and column names (16 mutants)

`_load_rows("turn_id = ?", …)` → `"XXturn_id = ?XX"`. Tests exercise these paths through
data they inserted themselves, so a predicate that matches nothing still returns what the
test expects. Ground truth has to come from rows the query was not told about.

### C6 — accumulators (26 mutants)

`acc.hook_output_tokens += int(row[…])` → `= …` (only the last row counts) or `-= …`
(sign inverted), concentrated in `execution_ledger._aggregate`. **These survive only if
every test aggregates a single row.** One test with three rows of differing values kills a
large fraction of C6 at once, and this is a money path.

### C7 — boundary and null-check flips (33: 13 boundary, 20 equality)

`if pending <= 0` → `< 0`; `if cost_usd <= 0` → `< 0`; `best_score >= _CONFIDENCE_THRESHOLD`
→ `>`; `if rates is not None` → `is None`. Small class, highest defect-density per mutant:
these are exactly the off-by-one and inverted-guard bugs that reach production. Each needs
a test at the boundary value itself — 0, and the threshold exactly.

### C8 — OS/IO notification shims (66 mutants, 2 functions) — **owner decision, §5**

`cost.fire_budget_alert` (38) and `router._native_notify` (28) are ranked #2 and #4 by
survivor count, so they look like prime targets. They are not, and the reason is in §5.

---

## 4. The 57 timeouts are OPEN, not explained

38 of 57 sit in two functions: `router._task_aware_default_order` (22) and
`router._reorder_for_agent_context` (16); the rest are scattered across regex and
complexity helpers.

**I have not instrumented these and will not guess.** A mutant that hangs may be an
infinite loop, catastrophic regex backtracking, or a slow test that the mutation pushed
past the limit — those imply different work, and on this codebase reasoning from source
went 0/5 while measurement went 3/3. Doc 20 §4 counts them as survivors either way, so the
score is unaffected by the answer.

**First action of Step 3** is to run one of these mutants under the harness and observe
where it hangs. Recorded here so it cannot later be closed with whichever story sounds
best.

---

## 5. Where killing a mutant would make the suite worse

Recorded now, before any test is written, so it is not discovered as a convenient excuse
later.

**C8, the notification shims (66 mutants, 11% of the gap).** These functions hand argv to
`subprocess.run` and have no in-process behaviour. The surviving mutations include
`"osascript"` → `"XXosascriptXX"`, `"osascript"` → `"OSASCRIPT"`, and `timeout=2.0` →
`3.0`. Killing them requires asserting on the exact argv and keyword arguments of a
subprocess call — a change-detector test that fails on any refactor and detects no defect
a user could observe.

Some of this is legitimate: invoking the *correct binary* is a real contract, and the
`sys.platform == "darwin"` → `!=` mutants encode a real platform-dispatch bug. The
notification *timeout value* is not a contract.

**This is an owner decision, and the honest options are:**

| option | effect on the gap | cost |
|---|---|---|
| (a) test argv fully | −66 mutants | 2 brittle change-detector tests |
| (b) test platform dispatch and binary name only | −25 to −35 (estimate, not measured) | proportionate |
| (c) exclude both functions from G-F scope | −66 from numerator **and denominator** | a third amendment |

**Recommendation: (b).** It is the only one that buys score by testing something that can
actually be wrong. (c) is a scope change to a pre-registered protocol and should not be
taken to make a number move.

**Genuinely equivalent mutants also exist.** `json.dumps(payload, separators=(",", ":"))`
→ `json.dumps(payload, )` produces different whitespace and identical parsed data; if
nothing asserts on byte-exact serialisation, no behavioural test can kill it. These are
unkillable by construction, they are counted as survivors under §4, and the count is
currently unknown. Doc 20 §4 chose conservative scoring deliberately, so this is a known
cost of the protocol and not a defect in it.

---

## 6. The 8 unclassified, enumerated

Listed rather than bucketed, so the 98.7% figure can be audited:

| function | mutation |
|---|---|
| `budget.invalidate_cache` | `_cache.pop(provider, None)` → `pop(None, None)` |
| `coverage.clear` | `_cached_snapshot = None` → `= ""` (sentinel change) |
| `execution_ledger.get_turn_accounting` | trailing positional arg dropped |
| `router._auth_error_hint` | `provider.lower()` → `.upper()` |
| `router._is_content_filter_error` | `str(exc).lower()` → `.upper()` |
| `router._param_size_hint` | `name.lower()` → `.upper()` inside `re.search` |
| `tool_surface.phantom_tools` | `if not implemented:` → `if implemented:` |
| `tool_surface.resolve` | `.strip().lower()` → `.strip().upper()` |

Five are case-folding on a method call rather than a literal — a real class the rules
score as `string_case` only when it appears on a literal. Two are negation flips. All
eight are killable behaviourally; none change the plan.

---

## 7. Step 3 work order

Ordered by mutants-per-test, not by mutant count, so effort buys score:

| # | class / function | mutants | why first |
|---|---|---|---|
| 1 | §4 timeout instrumentation | 0 | answers whether 57 are reachable at all before planning around them |
| 2 | C6 accumulators — `_aggregate` | ~51 | one multi-row test, money path |
| 3 | C1 fail-open codes | 40 | one pattern × 11 sites; closes finding #32's blind spot |
| 4 | the six 100%-uncovered functions | 92 | no test exists; any test scores |
| 5 | C7 boundary/null flips | 33 | highest real-defect density |
| 6 | C3 + C2 + C4 defaults, env, ordering | 35 | cheap, mechanical |
| 7 | `tool_surface.resolve`, `_extract_retry_after` | 64 | large single functions |

Per doc 21 Step 3: RED before / GREEN after with the red **proven by reverting the fix**;
assert on behaviour, never source text; never re-implement production logic in the test
body. Score TRAIN after each class, VALIDATION only at checkpoints. A widening
train/validation gap means overfitting — generalise rather than add tests.

## 8. What this does not claim

The score is 0.5866 and the floor is 0.80. Nothing in this document moves either number;
it is a map of where the missing tests are. The upper-bound column in §1 is arithmetic on
the assumption that covered functions get fully killed, which §5 already shows is false
for at least 66 mutants. **G-F remains NOT QUALIFIED.**
