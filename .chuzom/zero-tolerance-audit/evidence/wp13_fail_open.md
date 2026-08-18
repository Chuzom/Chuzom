# WP-13 — fail-open triage

Date: 2026-08-12. Finding RED8-09.

---

## The defect was the silence, not the catch

~810 broad `except Exception` handlers exist across the codebase, and most are
correct. A UserPromptSubmit hook that raises kills the user's turn. A telemetry
write that raises turns observability into an outage. Removing them would trade a
known degradation for a crash.

What made them defects in the money/routing paths is that they left **no trace**.
A handler ending in bare `pass` is indistinguishable from the happy path in every
surface we have — the same shape as the ledger drop that looked like no traffic,
the routing bypass that looked like a clean run, and the savings query that
rendered "$0.00 saved". A caught exception is information; discarding it converts
a known failure into an unknown one.

## Criteria

| Criterion | Result |
|---|---|
| Zero bare `except Exception: pass` in the five protected modules | **42 → 0**, `CHZ-FO-01: clean`, exit 0 |
| Every retained broad catch logs with a stable event code and increments a counter | 42 site-specific codes via `chuzom.failopen.record` |
| CI lint prevents new bare catches in the protected set | `Fail-open guard (CHZ-FO-01)` in `ci.yml` lint job |

Per-module: `cost.py` 17, `router.py` 21, `summary.py` 2,
`execution_ledger.py` 1, `dashboard_data.py` 1.

Codes name the SITE's behaviour, not the exception type.
`CHZ-FO-COST-CAP-LEDGER-READ` tells an operator which control degraded;
`OSError` does not.

## `chuzom/failopen.py`

Append-only JSONL, one `O_APPEND` write per event (same reasoning as
`chuzom.coverage`: short-lived processes, no lock on a hot path). Design
constraints, each from an earlier work package:

- **Never raises.** Every caller is already inside a handler that exists because
  propagating was unacceptable. An accounting call that can throw converts a
  fail-open into a crash — strictly worse than the silence it replaces. Tested
  against a broken store AND against an exception whose `__str__` itself raises.
- **Unknown is not zero.** An unreadable store reports `None`/"Unknown", never 0.
- **No `other` bucket.** A new site must add a code rather than hide in a count.

## Two money controls, and what "fail closed" actually meant for each

Owner decision 2026-08-12: fail closed on both. They needed different fixes, and
the second one's framing was wrong when it was raised.

### `CHZ-FO-COST-CAP-LEDGER-READ` — genuinely failing open

`_rejected_attempt_spend` sums billable-but-rejected attempts (RED1-08).
`get_daily_spend()` returns `winning + rejected`, compared against the cap at four
router sites. It returned **0.0** on any read error, which under-reports spend, so
**the cap check passes**. A guard that could not read the ledger did not reject —
it silently approved. Same direction as #19 and as "$0.00 saved": failing where it
looks harmless, which is why it survived.

Now returns `inf`, so every cap comparison denies. Routing continues (free and
local providers do not consult the cap); money is simply not spent against a total
we cannot account for.

**An overreach my own RED test caught.** The first version returned `inf` for
every exception — including `no such table`, which on a fresh install is the
normal state and genuinely means zero rejected attempts. That would have denied
every paid route on a new machine until the first ledger write: an outage dressed
as prudence. Fail closed on the unknown, not on the known-empty.

Display is guarded separately: `format_spend_for_display()` renders non-finite as
"Unknown", and the budget panel says so rather than drawing a bar from a NaN
percentage. `inf` is correct for a comparison and a fabrication on a dashboard.

### `CHZ-FO-ENVELOPE-STRANDED` — already failing closed; the defect was permanence

This one was mis-framed when raised, including by me. A failed
`release_envelope` **already fails closed**: the reservation stays held, so the
system believes it has *less* headroom and denies more. The direction was never
wrong.

The real defect is that the leak is **permanent and unreconcilable** — headroom
shrinks monotonically across a process's life and nothing records how much was
stranded. So the fix is not to change the direction but to make the loss
recoverable: retry once (a transient backend blip is the common cause and a second
attempt costs nothing on an already-failed path), then record the **amount and
key**. `"$0.0400 stranded on key X"` can be reconciled; `"release failed"` cannot,
and a slow leak would otherwise present only as "routing got stingy for no reason".

## Ledger emission was silently dropping events

`CHZ-FO-ROUTER-LEDGER-EMIT` and `-LEDGER-TERMINAL` swallowed failures to emit
ledger events. WP-06 hardened the ledger against **losing events under
concurrency**; these lost them **before arrival**. A reconciliation gap would have
been the only symptom. Now counted.

## Lint limitation, stated rather than hidden

`_leaves_a_trace` matches on the CALLED NAME, so
`from chuzom.failopen import record as _fo; _fo(...)` reads as untraced — and
conversely a local helper named `log_nothing()` would read as traced. Found the
hard way: the first three fixes in this very work package aliased the import and
the lint did not count them.

Deliberately **not** fixed by chasing aliases through the AST. That trades a
visible limit for an invisible one: the check would then look complete while
still missing indirection through a wrapper, a dict dispatch, or a decorator.
Given how many guards this audit found that were present, running and green while
blind, an honest limit beats a convincing one. Call sites use the canonical
`failopen.record(...)`, which is also what makes a code greppable.

## Process note for the re-audit

The first full-suite run for this work package reported two failures in
`tests/test_chz_aud_019.py` that do not reproduce. Cause: source files were edited
**while that suite was running**, so pytest collected some modules pre-edit and
others post-edit. The result is unattributable in either direction — an
unattributable red is worth no more than an unattributable green — and it was
discarded and re-run against a frozen tree.

The stated rule had been "never run two full suites concurrently". The actual rule
is broader: **never change the tree under a running suite.**
