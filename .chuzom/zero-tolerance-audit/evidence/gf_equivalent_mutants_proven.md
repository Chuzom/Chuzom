# G-F — the first PROVEN equivalent mutants

Date: 2026-08-15, while planning class C4 (ordering arguments). Doc 20 §4 counts
equivalent mutants as survivors by design; this records the first set proven to be
equivalent rather than merely suspected.

## The claim

Five mutants in `tool_surface.localize` cannot be killed by any behavioural test, because
the code they mutate has **no observable effect on the current data**.

    text = _re.sub(r"\b(" + "|".join(sorted(DEPRECATED_TOOLS, key=len, reverse=True)) + …)
    for legacy in sorted(DEPRECATED_TOOLS, key=len, reverse=True):
        if legacy in text:
            text = text.replace(legacy, resolve(legacy, slim).display)

The mutations: `key=len` → `key=None`, `key=` dropped, `reverse=True` → `reverse=False`,
`reverse=` dropped.

## Why the ordering exists

The docstring states the reason: *"Bare names, longest-first so no name is rewritten as a
prefix of a longer one."* The second pass uses `str.replace`, which has **no word
boundary at all** — so if `llm_code` were processed before `llm_code_review`, the longer
name would be corrupted mid-string into `llm(task="code")_review`.

The concern is real and the guard is correct.

## Why it is currently untestable — measured, not argued

`DEPRECATED_TOOLS` holds 25 names. Measured directly:

| check | result |
|---|---|
| names where one is a **prefix** of another | **0** |
| names where one occurs as a **substring** of another (what `str.replace` actually needs) | **0** |
| names occurring inside another name's resolved `display` | **0** |

With no name contained in any other, the replacement order is provably irrelevant:
every `replace` touches a disjoint set of positions. `key=len, reverse=True`,
`reverse=False`, and no key at all all produce identical output for every possible input
built from these names.

## Why a synthetic name does not rescue it

The obvious move — monkeypatch `DEPRECATED_TOOLS` to contain a prefix pair — does not
work, and the reason is worth recording:

    resolve('llm_code')        -> display 'llm(task="code")'     # rewritten
    resolve('made_up_name')    -> display 'made_up_name'         # returned UNCHANGED
    resolve('llm_code_review') -> display 'llm_code_review'      # returned UNCHANGED

`resolve()` returns an unknown name verbatim, so `text.replace(name, name)` is a no-op and
the ordering still cannot be observed. Killing these mutants would require monkeypatching
`DEPRECATED_TOOLS` *and* the resolution table — at which point the test asserts on a
fabricated world, and the standing rule against re-implementing production logic in a test
body applies.

**These five are equivalent mutants. Nothing is written for them.**

## What this means for the campaign

1. **The achievable ceiling is below 1.00.** Doc 20 §4's conservative scoring counts
   equivalent mutants as survivors deliberately, which is the right call for an audit —
   but it means a perfect suite would still not score 1.00, and the gap is unknown.
2. **It does not currently threaten the 0.80 floor.** Five proven-equivalent mutants out
   of 1986 is 0.25%. Only if the true equivalent-mutant rate were above 20% would the
   floor become unreachable in principle, and nothing observed so far suggests that.
3. **It is a reason to keep counting them honestly rather than excluding them.** Excluding
   equivalent mutants requires proving equivalence for each, which is exactly the work
   done above — and doing it case by case for hundreds of mutants would cost more than
   killing the killable ones.

## Method note

The proof is three `in`/`startswith` sweeps over real production data, not an argument
about what the code "should" do. That distinction matters: the same reasoning applied
*without* measuring would have concluded that longest-first ordering is load-bearing and
that a test was needed, and a test would then have been written that either passed
vacuously or asserted on a mock of the codebase's own tables.
