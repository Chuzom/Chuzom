# Chuzom Correctness Reset — 06. Session-Summary "Routing Dashboard" Discrepancies

Audit of the end-of-session summary rendered by `src/chuzom/hooks/session-end.py`
(the "Routing dashboard" a user sees at session end) and its sibling savings/routing
surfaces. The panels do **not** reconcile: the same underlying activity is priced,
counted, windowed, and labeled differently across sections, so the numbers can't be
made to agree. Method: three read-only audits (source-map + internal-consistency +
cross-surface) plus direct code verification.

**Scope:** these are all **read-only display surfaces** — the same low-risk class as the
already-shipped AC-4 fixes (digest #168 / dashboard #169 / admin #170). They do NOT
touch the live routing hook. Verdict stays **RELEASE NOT QUALIFIED** regardless.

Line numbers are against `main` @ the reset series (`#163–#173` merged); treat them as
anchors, re-grep before editing.

---

## Section source map (what each panel reads)

| Panel (fn) | Source | Window | Savings basis | Label |
|---|---|---|---|---|
| CC quota (`_format_cc_section`) | Claude OAuth API / `usage.json` | this-session delta | — (percent) | "session/weekly/sonnet %" |
| CC models (`_format_cc_model_section`) | `usage` WHERE provider=subscription | this-session | $0 (sub) | "subscription, $0.00" |
| Routing (`_format_routing_section`) | `usage` (paid providers) | this-session | **`_host_baseline(tokens)` recompute** | "saved" |
| Free (`_format_free_section`) | `usage` (free providers) | this-session | **`_host_baseline(tokens)`, Codex tokens ESTIMATED** | "saved vs Sonnet" |
| Cumulative (`_format_cumulative_section`) | `dashboard_data.query_window` (savings_stats ∪ usage ∪ platform) | today/week/14d/month/lifetime | **pre-computed `saved_usd`** | "Savings" |
| Codex (`_format_codex_section`) | `codex_usage` table | **today** | **stored `cost_saved_usd`** | "gross/overhead/realized" |
| Gemini (`_format_provider_section`) | `gemini_usage` table | **today** | **stored `cost_saved_usd`** | "gross/overhead/realized" |
| Routing logic (`_query_routing_logic`) | **`model_tracking.jsonl`** | start-of-day | — (method mix) | "avg routing / fallbacks" |

Four different savings bases and three different time windows sit in one report.

---

## Discrepancies (ranked)

### D1 — Four unreconcilable savings computations in one summary  · **HIGH**
The "saved" figure is computed four different ways: `_host_baseline(tokens)` recompute
(Routing, Free), pre-computed `saved_usd` from the `dashboard_data` UNION (Cumulative),
and stored `cost_saved_usd` from `codex_usage`/`gemini_usage` (Codex, Gemini).
`session-end.py:_format_routing_section` (~550), `_format_free_section` (~635),
`_format_cumulative_section` (~1144), `_format_codex_section` (~1417),
`_format_provider_section` (~1361).
**Why it can't reconcile:** different baselines, token sources, and windows → the
per-panel "saved" values don't sum to any consistent total; a reader adding them
double-/mis-counts. Violates INV-COST-004 (one canonical savings source per surface).

### D2 — Codex savings double-counted  · **HIGH**
Codex is in `_FREE_PROVIDERS` (`session-end.py:244`) so it renders in the **Free**
section, AND has its own **Codex** section (`_format_codex_section`, ~1417) reading
`codex_usage`. The same Codex activity produces a "saved" number in two panels, from two
sources, computed two ways.
**Why:** the Free panel prices Codex via `_host_baseline(estimated_tokens)`; the Codex
panel reads stored `cost_saved_usd`. The two figures disagree and are both shown.

### D3 — Codex "saved" built on fabricated tokens  · **HIGH**
The Free section has no Codex token counts, so it **estimates** them from the average
tokens/call of paid rows (fallback 500↑/300↓) and prices that
(`_format_free_section` ~646–649, 676). `saved` from invented tokens is then summed into
`total_saved`.
**Why:** the number is not measured. A `~est` tag is shown but the value still feeds the
panel total and disagrees with the real `codex_usage.cost_saved_usd` (see D2).

### D4 — "saved vs Sonnet" mislabel on the Opus/host baseline  · **MEDIUM**
Free section prints `"$X saved vs Sonnet"` (`_format_free_section` ~698) while
`_host_baseline` uses `HOST_INPUT_PER_M`/`HOST_OUTPUT_PER_M` = the **host frontier (Opus)**
rate (`session-end.py:53–59`, `_host_baseline` ~424).
**Why:** identical mislabel class fixed in digest (#168) and admin (#170) — the baseline
is the Claude host rate, not Sonnet. Fix: "vs Claude host baseline".

### D5 — Mixed time windows presented as one dashboard  · **MEDIUM**
this-session (Routing, Free, CC-models) sits beside today-only (Codex, Gemini) beside
today/week/14d/month/lifetime (Cumulative), with no per-panel window label on several.
**Why:** a reader can't tell which window a given "saved"/"calls" refers to; a session
number and a lifetime number appear side by side unlabeled → they look comparable but
aren't.

### D6 — Routing-method mix from a different store than the counts  · **MEDIUM** · ✅ FIXED (DASH-4)
`_query_routing_logic` reads `model_tracking.jsonl` grouped by `classification_method`
(start-of-day), while the fallback-rate total comes from the `routing_decisions` table.
Both are "today" but they are independent logs, so their totals legitimately differ.
**Fix (DASH-4):** attribution, not forced equality — the classifier-log count is now
"{n} classified … today · classifier log" and the routing-decisions total is "{n} routed",
so the two denominators name their sources and are not misread as one. Behavioural +
source-guard tests in `tests/test_dash4_routing_source_labels.py`.

### D7 — Free-provider "saved" credits the full host baseline without host-mode framing  · **MEDIUM**
Free section: `saved = max(0.0, baseline)` because free providers cost $0
(`_format_free_section` ~677). On a subscription/flat-rate host this is quota offset
(potential), not cash.
**Why:** same P0-2/AC-2 issue — full-baseline shown as "$ saved" without the subscription
caveat. Fix: host-mode-aware label ("quota freed" / "potential" on subscription).

### D8 — Stale fallback price diverges from sibling surfaces  · **LOW**
`session-end.py` fails open to **15/75** if the `cost.py` import fails (`:57–58`), whereas
digest (#168) and dashboard (#169) fall open to **5/25**.
**Why:** on the rare import failure, the session summary would show a 3×-inflated baseline
while every other surface shows the current price. Fix: unify the fallback to 5/25.

### D9 — Net-vs-gross savings shown inconsistently across panels  · **LOW**
Codex/Gemini panels show gross − overhead = **realized** (`_format_codex_section` ~1466,
`_format_provider_section` ~1408), while Routing/Free show **gross** saved with no overhead
netting.
**Why:** "saved" means realized-net in two panels and gross in two others — the same word,
two definitions (INV-COST-005 not applied uniformly).

---

## Fix plan → tasks (each a low-risk display-surface PR, own branch, fail-before/pass-after test)

- **DASH-1a (D2 + D3) — ✅ DONE (PR pending):** the two unambiguous display-honesty
  parts. (D2) Exclude Codex from the Free split — Codex is logged to *both* `usage`
  (`cost.log_usage` forces `cost_usd=0`, cost.py:706) and `codex_usage`, so the Free
  section double-counted it against the dedicated `_format_codex_section`. Fixed via a
  `_DEDICATED_PANEL_PROVIDERS = {"codex"}` exclusion at the `_query_session_data` split.
  (D3) `_format_free_section` no longer fabricates tokens from unrelated paid-call
  averages — unknown token volume renders `—` and claims `$0`. Behavioural fail-before/
  pass-after tests in `tests/test_dash1a_codex_dedupe.py`.
- **DASH-1b (D1) — DEFERRED (structural/semantic, own task):** unify onto ONE savings
  basis. Free + routing panels recompute `_host_baseline` (Opus); the Codex/Gemini panels
  render stored `cost_saved_usd` (a *different* basis); the star-CTA lifetime figure is a
  third. Reconciling them changes the **meaning** of the displayed Codex/Gemini numbers
  (recompute-from-tokens vs stored), so it is not a low-risk display edit — it needs a
  deliberate basis decision. Test target: for a seeded session, Σ panel savings == one
  canonical session total.
- **DASH-2 (D4 + D7 + D8):** Honest labels + fallback. "vs Sonnet" → "vs Claude host
  baseline"; host-mode-aware "saved"/"quota freed"; fallback 15/75 → 5/25. Source-guard
  test (no "vs Sonnet"; fallback == 5/25) mirroring `test_sessionstart_digest_uses_opus_not_sonnet_baseline`.
- **DASH-3 (D5):** Explicit per-panel window labels (and/or unify the "this session"
  panel). Test: each savings/counts panel string carries its window.
- **DASH-4 (D6):** Derive routing-method mix and call counts from one store/window
  (routing_decisions or usage), not `model_tracking.jsonl` vs `usage`. Test: method-count
  total == call-count total for a seeded session.
- **DASH-5 (D9):** One definition of "saved" across panels (realized-net everywhere, or
  label gross vs realized). Test: label consistency / net==gross−overhead everywhere shown.

DASH-1b and DASH-4 are the structural ones; DASH-1a/2/3/5 are label/window/dedup honesty
(fastest). All are read-only display fixes — no live-routing change; verdict stays NOT
QUALIFIED.
