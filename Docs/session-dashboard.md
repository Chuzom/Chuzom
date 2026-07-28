# Session Summary Dashboard & Streaming Progress

## Real-time streaming progress

Long-running model calls stream live progress into Claude Code. You'll see what's
happening inside Codex and Gemini CLI instead of staring at a blank spinner.

### Codex streaming (JSONL events)

Codex CLI emits structured JSONL events line-by-line. Chuzom forwards them as MCP
notifications:

```
⏺ Calling chuzom…
  ✅ thread.started
  ✅ turn.started
  ⚡ item.completed  — Analyzing the error stack...
  ⚡ item.completed  — The root cause is a missing null check in line 42
  ✅ turn.completed  — done — 1024 tokens
```

### Gemini CLI streaming (line-by-line)

```
⏺ Calling chuzom…
  ⚡ line  — The function signature should be...
  ⚡ line  — Here's the corrected version:
  ⚡ line  — def process(data: list[str]) -> dict:
```

### Heartbeat notifications

For all models, Chuzom sends periodic heartbeat notifications during long waits:

```
⏺ Calling chuzom…
  ⚠️  gpt-5.4 (codex) still waiting... 30s
  ⚠️  gpt-5.4 (codex) still waiting... 60s — may be overloaded, will auto-fallback on timeout
```

---

## Session summary dashboard

At the end of every Claude Code session, Chuzom prints a full-color session summary in
the terminal (the **Tokyo Night** palette).

```
╭────────────────────────────────────────────────────────────────────╮
│                                                                    │
│  ROUTING  today  181 decisions          SAVINGS  all sessions      │
│                                                                    │
│    ⚡ heuristic     94   52%              $37.70    1.2M tok       │
│    🔨 build-fast    36   20%            lifetime                   │
│    🔄 fallback      24   13%              $11.04    382.1k tok     │
│    🔗 ctx-inherit   10    6%            today                      │
│    📝 content-gen    2    1%              $36.15    1.1M tok       │
│    🔍 introspect     1    1%            week                       │
│                                                                    │
│    Zero-cost: ━━━━━━━━━━── 87%            ⚡ $0.10/hr              │
│                                           ~$0.76/active-day        │
│    Policy ⚖️  balanced                                             │
│    Effective: ━━━━━━━━━━━━ 88%                                     │
│    Escalated 21 (100%)                                             │
│    vs typical ↓↓ 0.1× cost                                         │
│                                                                    │
│    QUOTA  Claude Subscription  live                                │
│     5h  ━───────────────  7%                                       │
│    resets in 4h 49m (1:59am local)                                 │
│     weekly ━━━━━───────────  35%                                   │
│    resets Monday                                                   │
│                                                                    │
│    MODELS  this session                                            │
│    gemini-2.5-flash       3×   32.6k  $0.09                        │
│    gemini-2.5-pro         2×   47.0k  $0.16                        │
│    total                  5×   79.6k  $0.26   saved $0.00          │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯

🎨  Full colored summary: cat ~/.chuzom/last_summary.ansi  (or: chuzom summary)

  🧮 Routing Summary — this session
  Tier              | Calls | Tokens |   Actual |  Baseline |    Saved
  ──────────────────────────────────────────────────────────────────
  Free local        |    16 |    240 | $ 0.0000 | $  0.0013 | $ 0.0013
  Free subscription |     5 |   3516 | $ 0.0000 | $  0.0190 | $ 0.0190
  Paid API          |    27 |  13421 | $ 0.1735 | $  0.0725 | $ 0.0000
  ──────────────────────────────────────────────────────────────────
  TOTAL             |    48 |  17177 | $ 0.1735 | $  0.0928 | $ 0.0203
  Effective savings ratio: 0.53×
  ════════════════════════════════════════════════
```

### Dashboard panels

| Panel | What it shows |
|---|---|
| **ROUTING** (left, cyan) | Decision method breakdown with count + %; zero-cost bar; policy; effectiveness score; escalation/fallback rate; cost vs. typical session |
| **SAVINGS** (right, green) | Savings in USD + tokens per window; burn rate ($/hr) and ~8h active-day forecast |
| **QUOTA** (amber) | Claude 5h + weekly quota bars with reset countdown; shown only when subscription is active |
| **MODELS** | Per-model call count, tokens, and cost for this session |
| **14-DAY ACTIVITY** | Three side-by-side bar charts: **calls/day**, **savings/day**, **tokens saved/day**; real date x-axis; footer with totals, averages, and p95 latency |
| **Routing Summary** (plaintext) | Per-tier breakdown (Free local / Free subscription / Paid API) — calls, tokens, actual cost, baseline, and net saved |

### Reading the SAVINGS column

The right column is narrow (~28 chars), so each savings entry spans two lines — amount +
tokens first, then the time-window label.

- **`⚡ $0.10/hr`** — session burn rate (amber = moderate, red = >$1/hr)
- **`~$0.76/active-day`** — projected daily cost at ~8 active hours/day (not 24/7)

### Reading the Routing Summary table

| Tier | What's counted |
|---|---|
| **Free local** | Ollama, llama.cpp, vLLM, LM Studio (`openai_compat`) |
| **Free subscription** | Codex (OpenAI Max), Gemini CLI (Google One), Claude Code |
| **Paid API** | Cloud APIs billed per-token (OpenAI, Anthropic, Gemini API, etc.) |

**Baseline** = what those tokens would cost at Claude Sonnet rates. **Saved** =
baseline − actual (zero for Paid API rows where actual exceeds the baseline).
