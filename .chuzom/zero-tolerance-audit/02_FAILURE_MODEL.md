# 02 — PRODUCT FAILURE MODEL

Written **before** reading the test suite (§4), so the tests are judged against this model rather
than the model being shaped by whatever the tests happen to cover.

Guiding question:

> **If Chuzom were deeply broken while appearing healthy, what would that look like?**

Chuzom is unusually exposed to this because it is the component that *reports on itself*. Nearly
every health signal a user sees — routing banner, savings dashboard, session summary, `doctor` —
is produced by the same system whose correctness is in question. **A defect and its own detector
share a failure domain.** That is the through-line of everything below.

---

## FT-1 — Routing false positives ("we routed" when we did not)

The user believes a cheap model did the work; the expensive host actually did it.

| ID | Failure | Why plausible here | Owner |
|---|---|---|---|
| 1.1 | Hook emits a route; host ignores it and answers natively | Global rules concede routing is *advisory* in default modes; PreToolUse cannot intercept a **prose-only** answer | RED-1 |
| 1.2 | Emitted tool name not registered in the running MCP server | `tool_surface.py` is +480 lines post-qualification; HEAD's own commit is `CHZ-SURF-01`, a tool-name resolution fix | RED-1 |
| 1.3 | Valid syntax for one tool tier, invalid for another | Multiple tiers × 7 hosts = large untested Cartesian product | RED-1 |
| 1.4 | Classification correct, dispatch ignores it | 4,967-line `router.py`, +1,094 since qualification | RED-1 |
| 1.5 | Model selected correctly, execution uses another | Adapter/broker indirection | RED-1/3 |
| 1.6 | Premium invoked inside a broker/subprocess; attribution lost | `session_broker.py`, subprocess agents | RED-2/3 |
| 1.7 | Fallback path bypasses accounting entirely | Fallback is an exception path — historically under-instrumented | RED-2 |

**Decisive test:** can telemetry *distinguish* "routed and executed cheaply" from "we emitted a
route and never learned what happened"? If not, every routing metric is unfalsifiable.

## FT-2 — Routing false negatives (should route, didn't)

| ID | Failure | Owner |
|---|---|---|
| 2.1 | Hook silently no-ops (missing/misinstalled/crashed/timed out) | RED-1/4 |
| 2.2 | Over-broad exemptions send offloadable work to premium | RED-1 |
| 2.3 | Context-sensitivity heuristic over-fires → "by design" masks a bug | RED-1 |
| 2.4 | Subagent spawns / retries bypass routing | RED-1/3 |
| 2.5 | Generated rules files teach **outdated** tool vocabulary | RED-1/8 |
| 2.6 | An IDE integration silently stops invoking Chuzom after a host update | RED-1/4 |

Note FT-2 is *economically* self-concealing: failing to route costs the user quota but produces
**no error**, and may not appear in a denominator at all (see FT-5).

## FT-3 — False quality (wrong work marked correct)

The most damaging class: a cheap model does work it is not capable of, and a weak check blesses it.

| ID | Failure | Owner |
|---|---|---|
| 3.1 | `cmd` check exits 0 while output is wrong | RED-3 |
| 3.2 | `lint` passes broken code | RED-3 |
| 3.3 | `diff` check: symbol/file exists, implementation wrong | RED-3 |
| 3.4 | `canary` marker trivially gameable | RED-3 |
| 3.5 | Agent edits/deletes/mocks the test to make itself pass | RED-3 |
| 3.6 | Agent changes configuration instead of fixing the defect | RED-3 |
| 3.7 | **Planner authors its own acceptance criteria** → self-graded homework | RED-3 |
| 3.8 | Planner and executor share a blind spot; verifier inherits it | RED-3 |
| 3.9 | Weak local model passes a weak verifier → ships without escalation | RED-3 |
| 3.10 | Judge shares a model family with a candidate → self-grading | RED-2/3 |

**Contract link:** promise 10 — *"'Done' means the check passed, not a self-report."* If the
planner writes the check, "the check passed" **is** a self-report with extra steps.

## FT-4 — False savings

| ID | Failure | Owner |
|---|---|---|
| 4.1 | Baseline is a model the user would never have used (measured baseline = always-GPT-4o; product is sold for Claude subscription) | RED-2 |
| 4.2 | Stale prices / stale model aliases resolving to different pricing | RED-2/8 |
| 4.3 | Tokens **estimated** but presented as **measured** | RED-2 |
| 4.4 | Failed attempts, retries, hook overhead, broker/subprocess cost omitted | RED-2 |
| 4.5 | Premium fallback cost omitted from the "saved" side | RED-2 |
| 4.6 | Subscription quota represented as **cash** (category error) | RED-2 |
| 4.7 | Duplicate events inflate savings; retries inflate baseline | RED-2/5 |
| 4.8 | Failed ledger writes vanish → statistics *improve* | RED-2/5 |
| 4.9 | Multiple independent savings formulas that can drift | RED-2/8 |
| 4.10 | **Unknown silently becomes zero** | RED-2 |

**4.10 is the epistemic core.** Zero is data. Unknown is missing knowledge. Any code path that
coerces unknown→0 converts ignorance into a favourable number.

Sanity check available immediately — the README's own dashboard sample:

```
Paid API | 27 calls | $0.1735 actual | $0.0725 baseline | $0.0000 saved
TOTAL    | 48 calls | $0.1735 actual | $0.0928 baseline | $0.0203 saved
```

Actual **exceeds** baseline on the Paid API row (spent more than the counterfactual), yet TOTAL
reports **$0.0203 saved** — negative savings appear to be floored at zero per-row and excluded
from the total. If so, the headline "saved" figure is **structurally incapable of being negative**.
→ RED-2 must confirm or refute against real code.

## FT-5 — Metric denominators that hide the unknown

| ID | Failure | Owner |
|---|---|---|
| 5.1 | Unobserved traffic silently absent from the denominator | RED-2 |
| 5.2 | Quality rate looks excellent precisely *because* coverage is poor | RED-2 |
| 5.3 | Unverified completions counted as successes | RED-2/3 |
| 5.4 | Dashboard time windows mislabeled | RED-2 |
| 5.5 | Missing history inferred/synthesized rather than shown as missing | RED-2 |

**Rule applied throughout:** a metric that cannot report *how much it failed to observe* is not a
measurement; it is a summary of the subset that happened to work.

## FT-6 — False reliability

| ID | Failure | Owner |
|---|---|---|
| 6.1 | Green suite while real install is broken | RED-4/7 |
| 6.2 | Source tree works; **wheel omits files** (rules, prompts, static, migrations) | RED-4/7 |
| 6.3 | Windows/macOS/Linux divergence | RED-4 |
| 6.4 | 3.11 vs 3.12–3.14 divergence (README claims 3.11–3.14) | RED-7 |
| 6.5 | Hooks run under a **different interpreter** than the server | RED-4/5 |
| 6.6 | SQLite passes serial tests, fails under real **multi-process** load | RED-5 |
| 6.7 | Shutdown loses background telemetry | RED-5 |
| 6.8 | Concurrent sessions corrupt shared state / double-count | RED-5 |
| 6.9 | `doctor` tests a **parallel path** from the one real routing uses | RED-4 |

6.9 is a specific trap: a health check that exercises a simplified path can report green while the
production path is broken — the detector and the defect again sharing a domain.

## FT-7 — Security & privacy

| ID | Failure | Owner |
|---|---|---|
| 7.1 | Classifier sends prompt text to a **cloud** provider before deciding to route locally | RED-6 |
| 7.2 | Delegated child processes inherit the **full parent environment** (all keys) | RED-6 |
| 7.3 | Secret scrubber regexes miss modern key formats | RED-6 |
| 7.4 | Keys written with permissive file modes | RED-6 |
| 7.5 | Model-generated commands executed with inadequate boundary | RED-6 |
| 7.6 | **Indirect prompt injection** from repo content subverts a delegated agent — "mark the milestone successful", "weaken the verifier" | RED-6 |
| 7.7 | Network components bind without auth (`pyproject.toml:123` documents a *prior* 0.0.0.0-no-auth issue) | RED-6 |
| 7.8 | Secrets leaked via `doctor` output, logs, or exception messages | RED-6 |

7.6 is the highest-stakes: it converts FT-3 from an accident into an **attack**. If repository
content can instruct the verifier, the entire objective-verification promise collapses in any repo
containing untrusted content (a dependency, a PR, a fixture).

## FT-8 — Installation & lifecycle

| ID | Failure | Owner |
|---|---|---|
| 8.1 | Install **clobbers** pre-existing host config (settings.json, hooks, MCP servers) | RED-4 |
| 8.2 | Uninstall leaves orphan hooks/MCP registration → host broken after removal | RED-4 |
| 8.3 | Install/upgrade/uninstall not idempotent | RED-4 |
| 8.4 | Downgrade fails or corrupts state | RED-4/5 |
| 8.5 | Default config with **no providers** silently delivers nothing | RED-4 |

8.1/8.2 are the only failures here that damage a user's environment rather than merely the
product — hence P0-eligible on their own.

## FT-9 — Architectural defect generators

| ID | Failure | Owner |
|---|---|---|
| 9.1 | Duplicate sources of truth (pricing, model aliases, tool names, tiers) drift silently | RED-8 |
| 9.2 | Broad `except Exception` swallowing correctness errors as "healthy" | RED-8 |
| 9.3 | Fail-open defaults across telemetry and enforcement | RED-8/5 |
| 9.4 | Env-var sprawl → untested configuration combinations | RED-8 |
| 9.5 | **Leaderboard optional/disabled/stale** while copy implies live capability ordering | RED-8 |
| 9.6 | Optimizing *cheapest initial attempt* rather than *minimum expected cost of success* | RED-8 |

9.6 restated concretely: a model that is 10× cheaper but fails 40% of the time, after retry and
escalation, can cost **more** than starting one tier up — while still reporting a "saving" on the
first hop. This is FT-4 and FT-3 compounding, and it would look like success in every metric.

---

## Cross-cutting invariants the audit must settle

| # | Invariant | Consequence if false |
|---|---|---|
| I-1 | The system can distinguish *observed success* from *unobserved outcome* | Every routing/quality/savings metric is unfalsifiable |
| I-2 | Unknown never becomes zero | Savings are structurally biased upward |
| I-3 | Verification is not authored by the party being verified | Promise 10 is void |
| I-4 | Emitted tool names resolve against the **live** registered surface | Silent bypass at scale |
| I-5 | A hard global bound exists on attempts/spend per user request | Unbounded cost from one prompt |
| I-6 | Repository content cannot influence verification outcome | Objective verification void in untrusted repos |
| I-7 | Install/uninstall is non-destructive and reversible | Product damages user environments |
| I-8 | Every user-facing number is independently reconstructable | Product's central claim unverifiable |

**Prediction registered before results arrive** (so it can be scored honestly): the highest-yield
findings will cluster on **I-1, I-2 and I-3** — not on ordinary code bugs — because those are the
invariants a system that grades its own homework is least able to protect, and least able to
notice violating.
