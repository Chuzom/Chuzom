# Finding #23 — AUD-06 was fixed once and survived eleven times

Date: 2026-08-13. **P0.** Found during WP-16.

---

## How it was found, because the method is reusable

Not by reading the finding. By authoring the G-F baseline-era mutation set: a
helper searched for lines **identical and unique in both the pre-remediation tree
(`c2c2882`) and HEAD**, and one of the first hits was

```
cost.py:3136   saved_usd = max(0.0, host_baseline - actual_usd)
```

Identical across both trees means **the entire remediation never touched it**.

> Diffing HEAD against the pre-remediation tree for the patterns a finding
> claims to have fixed is cheap and high-yield. Anything a remediation left
> byte-identical, while claiming to have fixed that class of defect, deserves a
> look. The audit never ran this check.

## The defect

AUD-06: *"TOTAL saved is a **sum of wins, not a net** — losses clamped to zero
before aggregation."* Invariant **I-2** ("unknown/adverse never becomes
favourable") is recorded **FALSE** citing it.

WP-04/WP-05 fixed **`hooks/session-end.py`** and pinned it with
`tests/economics/test_savings_sign.py` — which loads **that one file**. `M3` in the
mutation sample reintroduces that one clamp and is killed. Everything looked closed.

**Twelve other sites kept the clamp.** Measured sweep, each triaged individually:

| site | verdict |
|---|---|
| `cost.py:3136` `get_team_savings` | **DEFECT — worst case, see below** |
| `cost.py:2953` per-call accumulate | **DEFECT** — clamps each call *before* summing: AUD-06's "sum of wins" verbatim |
| `cost.py:3211`, `cost.py:3229` | **DEFECT** — totals and per-model |
| `router.py:1926` `saved_usd=` | **DEFECT** — written into the ledger record, so it poisons *stored* data, not just a view |
| `digest.py:92` | **DEFECT** (metered branch) |
| `retrospective.py:461` | **DEFECT** |
| `route_server.py:125` | **DEFECT** |
| `tools/dashboard.py:169, 212` | **DEFECT** — per-day, per-provider |
| `tools/dashboard.py:278` | **DEFECT — the purest case** |
| `tools/dashboard.py:335` | **DEFECT** — missed by my own manual triage; the lint found it |
| `execution_ledger.py:582` | **LEGITIMATE** — see below |
| `quota_savings.py:354-363` | **NOT A DEFECT** — `max(0, 100 - pct*100)` is percentage *remaining* |

**`cost.py:3136` is the worst** because `get_team_savings` is called by
`team.py:293`, which **broadcasts to Slack/Discord**. The function's own comment
records that a prior audit finding (P0-2) was about this very function emitting
unqualified cash. A team that overspends gets **"saved $0.00" published to their
channel**.

**`dashboard.py:278` is the purest**: `total_saved = sum(saved) - classifier_overhead`,
then `net_saved = max(0, total_saved)`. Overhead exceeding gross reads as zero —
AUD-06's sentence, executable.

**`execution_ledger.py:582` is legitimate.** `potential_savings_usd` is documented
as "Σ max(0, baseline_eq − actual) over ALL routes" — an upside-only metric by
definition, sitting beside the **signed** `net_realized_savings_usd`. It is the
lint's single exemption, and a test asserts the exemption list stays at one.

## Why the fix is a module and a lint, not twelve edits

`13_HISTORICAL_DEFECT_PATTERNS.md` records the `$15/$75` price bug being fixed
locally **four separate times** and returning every time, *"because no fix was
ever made structural"*. The remediation for AUD-06 repeated exactly that: one
site fixed, twelve left. **Editing twelve call sites would have been the fifth
repetition** — the thirteenth surface someone writes would clamp again.

- `chuzom/savings.py::net_saved(baseline, actual)` — trivially `baseline - actual`.
  The value is not the arithmetic; it is that one place performs the subtraction
  and a lint can point at anything that does not use it.
- `scripts/lint_savings_sign.py` (**CHZ-SS-01**), wired into CI.
- Display fixed too: the dashboard's net figure is now coloured **by sign**
  (`_GREEN if >= 0 else _RED`) and formatted `:+.4f`. A negative rendered in green
  reads as a win — the display-layer half of the same defect, one layer after
  RED2-02's "$0.00 saved".

## The lint's first draft was wrong in both directions

Worth recording, because a gate this coarse would have been disabled within a week.

**Too broad.** Matching `max(0, <any subtraction>)` flagged 22 sites, including
nine `_pending_spend - _reservation` budget counters, a timespan
(`latest_ts - earliest_ts`), and **string padding** (`max(0, 60 - len(text))`).
All correct code. My own docstring had already argued that "a noisy gate gets
disabled, which is worse than a narrow one that is trusted" — and the first draft
was the noisy one. The match now requires savings vocabulary in the target, key,
keyword, or an operand naming a baseline.

**Too narrow, simultaneously.** It *missed* `dashboard.py:278` — the purest case —
because the subtraction happens on the previous line, so the call is
`max(0, total_saved)` with no `BinOp` inside. The rule now also flags a
zero-clamp on a savings-*named* value with no inline subtraction. Catching the
worst instance depended on the name, not the shape.

**And it found one I missed.** `dashboard.py:335` was not in my hand-triaged
list. The tool beat the human on coverage while the human beat the tool on
precision — which is the argument for having both, and for not shipping either
alone.

## Verified to fire

`test_chz_ss_01_actually_detects_a_clamp` copies the money modules to a tmpdir,
confirms the copy starts clean, reintroduces `saved = max(0.0, baseline - cost)`
in `digest.py`, and asserts CHZ-SS-01 returns 1. A lint that passes on a clean
tree is otherwise indistinguishable from a lint whose matcher is broken.

While checking the lint's own exit code I once again read `$?` from the end of a
pipe (`lint | head`) and saw `0` for a failing run — the **third** time this
remediation that an outcome was taken from the wrong place instead of an exit
status. Caught immediately this time.

## What this does to the verdict

- **AUD-06 cannot be recorded closed** on the prior evidence; the claim was true
  of one file and false of the system.
- **I-2 was not restored**, so the invariant-restoration criterion could not have
  been honestly claimed.
- **G-A** — "any open P0 → verdict is FAIL" — was therefore already violated
  before this fix landed, independently of G-F's baseline problem.
- `test_savings_sign.py` remains immutable and untouched; coverage was extended
  in a new file.

The general lesson is narrower than "test more". It is: **a regression test that
loads one file proves one file.** The asset was correct, immutable, and green,
and its scope was mistaken for the finding's scope.
