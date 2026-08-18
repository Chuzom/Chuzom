# Finding #24 — RED2-02 survives where it is loudest: the broadcast

Date: 2026-08-13. Found by the deliberate "untouched by the remediation" sweep —
the method that accidentally found P0 #23.

---

## The chain, measured end to end

RED2-02 is *"failure reads as zero"*. The remediation built
`chuzom.provenance`, whose `Measured.render()` **never prints a number for
unknown**, and applied it to several surfaces — `cost.py` carries five
`"provenance"` keys. `get_team_savings` had **none**, on either path.

1. **`cost.get_team_savings`** — on a DB error returned bare zeros. Its own
   comment already said: *"Zeroes here render as 'you routed nothing and saved
   nothing' — a working install that looks idle."* WP-13 added
   `failopen.record(...)`, so the failure was **counted** — but internally. **A
   counter the caller cannot see does not stop a false broadcast.**
2. **`team.build_team_report`** — copies fields with `.get(key, 0.0)`, so any new
   key is silently dropped. An honest `cost.py` would have been undone here.
3. **`team._savings_label`** — rendered `"$0.0000 vs baseline (≈$0 cash on
   subscription)"`.

A team whose database is unreadable received **exactly the message a team that
had a quiet week receives**, published to their Slack or Discord channel.

## Fixed at all three layers, because any one of them re-hides it

- `get_team_savings` returns `provenance: "unknown"` + a detail on failure, and
  `"measured"` on success. **The success tag matters as much as the failure one**:
  if the key appeared only on the error path, a caller could not distinguish
  "absent because measured" from "absent because nobody set it".
- `build_team_report` forwards it, defaulting to **`"unknown"`**, not
  `"measured"` — defaulting to measured would launder an unmarked source into a
  confident report.
- `_savings_label` returns `Measured.unknown(detail).render()`, reusing the
  existing rule rather than inventing a second convention.

A test pins that a **genuinely quiet period still reads `$0.0000`**. A fix that
turned every quiet week into an alarm would be ignored within a month, and the
signal would be lost again by a different route.

## Two things the fix uncovered

**Only two of four renderers used the shared label.** Slack and Discord call
`_savings_label`; `_telegram_message` formatted `baseline`/`real` itself, and
`_generic_payload` passes the whole dict (so it was fine). Fixing Slack and
Discord alone would have been **the same "fixed some surfaces, assumed global"
shape as AUD-06 itself, inside the fix for it.** Telegram now routes through the
one renderer. Its wording changes slightly as a result — the `real > 0` case now
reads `"$X real · $Y vs baseline"` — which is the cost of having one renderer
instead of two, and worth it.

**`_get_db()` sat OUTSIDE the try.** So the *most likely* failure — the ledger
missing, locked, or permission-denied at open time — propagated as an exception,
while the `except` block covered only the rarer query failure. The test I wrote
to force the error path failed with the raw `RuntimeError`, which is how this
surfaced: **the test disagreed with my model of the code, and the code was
wrong.** `_get_db()` is now inside the try, with `finally` guarding `db is None`.
An honest "unknown" beats an exception a caller may swallow into a silent
broadcast.

## Two names I got wrong, both caught by running the tests

I wrote assertions against `generate_team_report` and `_savings_line`. The real
names are `build_team_report` and `_savings_label`. Both failed loudly on the
first run.

Worth recording only because the failure mode it *avoids* is the one this audit
keeps finding: had those been written as `getattr(team, "…", None)` guards or
wrapped in try/except, they would have passed while testing nothing — a
can't-fail test born from a typo rather than from intent.

## What it does not cover

The sweep that found this flagged more in the same family, each needing
individual triage — **untouched is a prompt to look, not proof of a defect**:

- 4 further zeroed-dict returns in `cost.py` (latency and cache-hit stats;
  likely benign, but check whether any feeds a money figure).
- 12 bare `return 0.0` in money modules.
- 11 untouched `except Exception:` in money/routing modules **outside the five
  `lint_fail_open` protects**. Notably **`team.py` broadcasts money and is not in
  that list** — the protected-module list is narrower than the surfaces that
  publish figures.
- 21 `or 0.0` coalescences.

And one clean result worth stating: **stale `$15/$75` price literals — zero
untouched occurrences.** That defect really was fixed structurally. It is the
counterexample showing this method finds signal rather than merely finding
things.
