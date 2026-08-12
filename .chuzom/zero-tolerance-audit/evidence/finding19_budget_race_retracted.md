# Finding #19 — RETRACTED. The budget guard is sound; the test is load-sensitive.

Date: 2026-08-12. Raised and retracted the same day.

---

## What I claimed

That `tests/audit/test_concurrency_determinism.py::test_concurrent_calls_cannot_exceed_monthly_budget_cap`
had exposed a real TOCTOU race — "a money control failing open", "the most
serious finding of the session", P0-adjacent for gate G-A.

**That was wrong.** It was asserted from a reproduction, not from a measurement
of the mechanism.

## What is actually true

Measured by sampling `router._pending_spend` from outside the code under test,
with zero source edits. Under CPU starvation, 4 runs out of 4 over-admitted AND
every one showed releases interleaving with admissions.

Timeline from one failing run (seconds since first sample, R = one reservation):

```
 0.0000  0.00 R
 0.0686  1.00 R     admit 1
 0.2025  2.00 R     admit 2
 0.6843  3.00 R     admit 3   <- cap now correctly blocks
 8.9949  2.00 R     release
 9.0003  1.00 R     release
12.0939  2.00 R     admit 4   <- 12s later, pending was 1R against a 2.5R budget
12.1044  1.00 R     release
12.1625  2.00 R     admit 5
15.7162  1.00 R     release
18.7278  0.00 R
```

Calls 4 and 5 were admitted roughly **12 seconds** after calls 1–3 had completed
and released. At that moment in-flight spend genuinely was 1R against a 2.5R
budget. **The guard admitted them because there was real headroom. That is
correct behaviour.**

Idle baseline for contrast: all three admits complete by t=0.066s and the first
release lands at t=5.39s — a five-second gap. The burst really is simultaneous
when the machine is not starved.

## The defect is in the test's premise

The test assumes all 10 calls reach the admission check **before any completes**.
Its own comment says so: the calls "all complete only after `_sleep_s`, so during
the concurrent admission burst it stays at 0 and the cap is governed purely by
the in-flight `_pending_spend` reservations".

That premise holds on an idle machine and fails under load, where a later call
may not reach the check for 12 seconds. The assertion then measures scheduling
skew, not mutual exclusion.

## Four hypotheses falsified before the right one

Each was plausible and each was checked rather than assumed:

1. **"The lock is missing."** No — RED1-09 already replaced a per-event-loop
   `asyncio.Lock` (zero mutual exclusion under the gateway's
   `asyncio.run()`-per-request model) with a process-wide `threading.Lock`.
2. **"Check and increment are in different lock blocks."** No — measured by
   indentation: lock opens at `router.py:3652` (indent 8), cap checks at
   3674/3703/3718 (indent 16), `_pending_spend += _reservation` at 3741
   (indent 12). All inside the lock body.
3. **"The router's reservation under-counts."** Real but negligible: router uses
   `_estimate_cost('gpt-4o', len(prompt)//4, 500)` = 0.005 while the test's
   expectation uses `max(1, ...)` = 0.0050025. Simulating admission with the
   router's value still yields exactly 3.
4. **"DB write lag."** Excluded by the test's own design — every call sleeps
   before returning, so `monthly_spend` stays 0 throughout the burst.

## Instrumentation notes, because they nearly produced a fifth wrong answer

Two attempts to instrument by editing `router.py` failed:

- The first wrote a broken f-string and the tests **errored**. The run reported
  "0/6 reproductions", which I nearly read as "does not reproduce". It measured
  nothing.
- The second used a blanket string replace that matched **15** sites instead of
  3, including decrements already inside `try:` blocks — another SyntaxError.

Both were caught only by explicitly checking whether the probe produced output.
The working approach edits nothing: a sampler task reads the module global while
the burst runs, so the instrument cannot break the thing it measures.

## What still stands

**CI runs the suite once, unloaded, so this assertion cannot fire there.** True
regardless of cause. As written the test provides no CI signal for the property
it names — it passes on an idle machine whether or not the guard works.

## Recommended disposition

- Re-classify #19 from "money control failing open" to "load-sensitive test".
- **Do not** change `_budget_lock`/`_pending_spend`. A fix aimed at this
  non-existent race could pass the test by coincidence and would add complexity
  to a guard that is doing its job.
- Fix the TEST so it measures what it claims: hold every call at a barrier until
  all 10 have reached the admission check, so no call can complete before the
  burst is fully admitted-or-rejected. Then the assertion tests mutual exclusion
  rather than scheduler timing, and it becomes meaningful in CI.
