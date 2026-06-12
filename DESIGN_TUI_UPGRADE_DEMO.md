# CHUZOM TUI Design Upgrade — Premium Terminal Interface

## Vision
Transform chuzom's terminal output from functional-but-basic to **premium, elite-tier CLI aesthetics** with:
- **True color palette** (Tokyo Night dark theme)
- **High information density** with surgical contrast control
- **Instant scannability** — metrics pop, structure dims
- **Cyberpunk minimalism** — clean lines, high-impact data visualization

---

## Color Palette (Tokyo Night Dark)

```
Primary/Accent:   #7aa2f7 (Cyan-Blue) — routing decisions, key metrics
Success:          #9ece6a (Vivid Green) — savings, success states
Warning:          #e0af68 (Amber/Gold) — alerts, warnings
Error:            #f7768e (Neon Pink) — failures, issues
Muted Borders:    #3b4261 (Deep Slate) — frames, dividers
Text Primary:     #c0caf5 (Off-White) — readable but cool
Text Dim:         #565f89 (Deep Gray) — labels, secondary info
Background:       #1a1b26 (Near Black) — main bg
Surface:          #192734 (Dark Navy) — panels, containers
```

---

## AREA 1: `chuzom status` — Routing Status Command

### BEFORE (Current)
```
──────────────────────────────────────────────────────────────
  chuzom status
──────────────────────────────────────────────────────────────

  Claude Code subscription  (3m ago)
    session (5h)     ███████░░░░░░░░░░░░░  34.0%
    weekly           ██████░░░░░░░░░░░░░░  30.0%
    weekly sonnet    █████░░░░░░░░░░░░░░░  24.0%

  Gemini CLI subscription
    daily quota      ░░░░░░░░░░░░░░░░░░░░  0.3% (4/1500)

  Routing savings
    today                 $10.298 saved  (200% cheaper)
    ██████████████████████████░░  83 calls
```

**Issues:**
- All-caps ASCII lines are loud and structural
- Numbers blend into labels (low scannability)
- Progress bars don't convey urgency/health
- Quota meters lack visual hierarchy

### AFTER (Proposed Premium UI)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  ⚡ CHUZOM Status  · Session 3m ago  · Health: Optimal     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 📊  Claude Code Subscription
   Session Quota (5h)       ████████░░ 34%  · 2.8h remaining
   Weekly Usage             ███████░░░ 30%  · 4.2d remaining
   Sonnet Monthly           ██████░░░░ 24%  · No pressure

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 💎  Routing Savings  [$16.62 lifetime · 72% cheaper]

   Today        $10.30 saved  ·  83 routed calls
   This week    $16.62 saved  · 1.7k routed calls
   This month   $16.62 saved  · 1.7k routed calls
   All time     $16.62 saved  · 1.7k routed calls

   Top models:    gpt-4o (577×) · claude-opus (180×) · gemini-2.5 (23×)
   Free routing:  codex 76×  ·  $0.63 saved vs Sonnet

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 🔧  Quick Actions
   ① chuzom dashboard      Launch live web dashboard
   ② chuzom doctor         System health check
   ③ chuzom update         Pull latest hooks

```

**Key Upgrades:**
- Muted `━` dividers (not screaming `─────`)
- **Vivid emojis** + accent colors only for changing data
- Smart grouping with hierarchy (section headers dim, metrics vivid)
- Remaining time callouts (user-centric)
- Model breakdown in one scannable line
- Action footer with numbered shortcuts

---

## AREA 2: Session Summary Dashboard (`chuzom stop` / hook output)

### BEFORE (Current)
```
╭────────────────────────────────────────────────────────────────────╮
│                                                                    │
│  ROUTING  today  84 decisions     SAVINGS  all sessions            │
│                                                                    │
│   ⚡ heuristic        35   42%     $16.62  lifetime                │
│   🔗 ctx-inherit      16   19%     $10.30  today                   │
│   🔗 ctx-inherit      12   14%                                     │
│   🔄 fallback          8   10%     today    $10.30    83 285.7k    │
│   🔨 build-fast        7    8%     week     $16.62  1680 522.0k    │
```

**Issues:**
- Confusing layout (labels ambiguous about what data belongs where)
- Methods are loud, savings are whispers
- No context on what "42% heuristic" means to the user
- Token numbers buried in dense rows

### AFTER (Proposed Premium UI)

```
╔════════════════════════════════════════════════════════════════════╗
║                   🎯  Routing Summary                              ║
║                    Session · June 12 · 17:30 UTC                   ║
╚════════════════════════════════════════════════════════════════════╝

┌─ Decisions by Method ───────────────────────────────────────────────┐
│                                                                     │
│  ⚡ Heuristic          35/84  (42%)  ███████████████░░░░░░░░░░░░   │
│  🔗 Context-Inherit    16/84  (19%)  █████░░░░░░░░░░░░░░░░░░░░░░   │
│  🔄 Fallback            8/84  (10%)  ██░░░░░░░░░░░░░░░░░░░░░░░░░   │
│  🔨 Build-Fast          7/84   (8%)  █░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│  📝 Content-Gen         2/84   (2%)  ░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│  ❓ Other               6/84   (7%)  █░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│                                                                     │
│  Zero-Cost:  100%  ████████████████████████████████████████  Safe   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─ Cost Savings Summary ──────────────────────────────────────────────┐
│                                                                     │
│  💰 Lifetime Savings     $16.62      (177% cheaper vs Opus)        │
│  📈 Today               $10.30      (200% cheaper vs Opus)        │
│  📊 This Week           $16.62      (177% cheaper vs Opus)        │
│                                                                     │
│  Free Routing:  codex 76× calls  ·  11k↑ 39k↓ tokens  ·  $0.63 ✓   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─ 14-Day Activity ───────────────────────────────────────────────────┐
│                                                                     │
│  Calls/Day (last 14d)                      Tokens/Day              │
│  ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔  │
│                                                                     │
│    391 ┤    █                                      2,847 ┤    █    │
│    335 ┤    █▁                                     2,398 ┤    █▁   │
│    279 ┤   ▄██                                     1,950 ┤   ▄██   │
│    223 ┤ ▅ ███▃                                    1,501 ┤ ▅ ███▃  │
│    167 ┤ █▆████                                    1,052 ┤ █▆████  │
│    111 ┤ ██████                                      603 ┤ ██████  │
│     55 ┤ ██████▅                                      154 ┤ ██▅    │
│      0 ┤ ███████                                        0 ┤ ███░   │
│        └────────────────────────────────────────────────└─────────  │
│         D-13  D-11  D-9  D-7  D-5  D-3  D-1              D-13  D-1  │
│                                                                     │
│  Avg: 240 calls/day  ·  365 tokens/day  ·  100% uptime  ✓          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─ Top Routed Models ────────────────────────────────────────────────┐
│                                                                    │
│  1. gpt-4o                    577×  ·  $5.77  (65% of routed $)   │
│  2. claude-opus               180×  ·  $1.80  (20% of routed $)   │
│  3. gemini-2.5-flash           23×  ·  $0.02  (0.2% of routed $)  │
│  4. gpt-5.4                     8×  ·  $0.00  (free tier)         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

  ✨ Session Complete  ·  Ready for next prompt

```

**Key Upgrades:**
- **Cleaner headers** with subtle separator lines (not loud boxes)
- **Method breakdown** with intuitive bar charts (not list)
- **Savings highlighted** in `💰` emoji + vivid accent color
- **Separate panels** for each metric type (decisions / savings / activity)
- **Mini charts** with day labels and context
- **Muted borders** (deep slate) vs data (cyan/amber/green)
- **Final status line** with timestamp (context)

---

## AREA 3: Live MCP Status (when routing in progress)

### BEFORE (Static)
```
Routing to llm_code...
```

### AFTER (Animated with Rich Status)

```
⚡ Classifying prompt...  [════════░░░░░░░░░░░░] 35%  ~2.3s
```

Using `rich.status.Status` with smooth animation:
```python
with console.status("[cyan]⚡ Routing[/cyan]...", spinner="dots"):
    # do work
    console.log("✓ Classification: [green]code/complex[/green]")
    console.log("→ Selected: [cyan]claude-opus[/cyan]  [dim](via heuristic)[/dim]")
```

---

## Architecture Plan

### Current State
- `status.py` — hand-rolled print() calls with ANSI color codes
- `session-end.py` — hand-rolled print() + Rich tables, 1679 lines
- `tui/` — Textual app for full dashboard, but underutilized

### Proposed Refactor

```
src/chuzom/ui/
├── __init__.py
├── theme.py                 # NEW: Central color palette (Tokyo Night)
├── components.py            # NEW: Reusable Rich components
│   ├── MetricBox()
│   ├── MethodBreakdown()
│   ├── SavingsPanel()
│   └── ActivityChart()
├── status.py                # REFACTOR: Use new components
├── session_summary.py       # REFACTOR: Extract from session-end.py
├── status_spinner.py        # NEW: Animated routing status
└── styles.py                # Centralized Textual CSS (from tui/)
```

### Key Components

**1. `theme.py` — Tokyo Night Palette**
```python
from rich.color import Color

COLORS = {
    "accent": "#7aa2f7",        # Cyan-Blue
    "success": "#9ece6a",        # Vivid Green
    "warning": "#e0af68",        # Amber
    "error": "#f7768e",          # Neon Pink
    "muted_border": "#3b4261",   # Deep Slate
    "text_primary": "#c0caf5",   # Off-White
    "text_dim": "#565f89",       # Deep Gray
    "bg": "#1a1b26",             # Near Black
    "surface": "#192734",        # Dark Navy
}
```

**2. `components.py` — Reusable Rich Widgets**
```python
class MetricDisplay:
    """Single metric with label + value + optional subtext."""
    def __init__(self, label: str, value: str, unit: str = "", subtext: str = ""):
        self.label = label
        self.value = value
        self.unit = unit
        self.subtext = subtext
    
    def render(self) -> Text:
        # Render with accent color on value, dim on label

class MethodBreakdown:
    """Breakdown of routing methods with %bars."""
    def render(self) -> Table:
        # Table: method name | count/total | bar | %

class SavingsPanel:
    """Savings summary with time windows."""
    def render(self) -> Panel:
        # Vivid savings $, dim time periods
```

**3. `status.py` — Refactored Command**
```python
from chuzom.ui.components import MetricDisplay, SavingsPanel
from chuzom.ui.theme import COLORS

def cmd_status():
    # Replace hand-rolled print() with component rendering
    metrics = [
        MetricDisplay("Session Quota", "34%", "/100%", "2.8h remaining"),
        MetricDisplay("Weekly Usage", "30%", "/100%", "4.2d remaining"),
    ]
    
    savings_panel = SavingsPanel(data=...)
    
    # Render with Console
    console.print(savings_panel.render())
```

---

## Implementation Roadmap

### Phase 1: Foundation (Isolated)
- [ ] Create `ui/theme.py` with Tokyo Night palette
- [ ] Build `ui/components.py` with core widgets
- [ ] Add tests for components
- [ ] **Status**: Can build in parallel without breaking current code

### Phase 2: Refactor Commands
- [ ] Rewrite `commands/status.py` → use components (this file you fixed!)
- [ ] Extract session summary rendering into `ui/session_summary.py`
- [ ] Update `hooks/session-end.py` to delegate to session summary module
- [ ] **Status**: Tests verify output matches before/after

### Phase 3: TUI Integration
- [ ] Update `tui/app.py` to use new palette + components
- [ ] Refactor `tui/panels.py` with component framework
- [ ] Animate status spinners for live routing feedback
- [ ] **Status**: Live dashboard now has premium aesthetics

### Phase 4: Polish
- [ ] Responsive resizing (handle terminal shrink/grow)
- [ ] Color mode detection (fallback to 256-color if needed)
- [ ] Documentation + style guide for future UI additions
- [ ] **Status**: Production-ready premium CLI

---

## Design Principles Checklist

- ✅ **True Color**: Hex-based palette (Tokyo Night), not 8-bit ANSI
- ✅ **Dim Noise**: Borders, dividers, labels in `#3b4261` (deep slate)
- ✅ **Pop Metrics**: Savings, routing decisions, timers in `#7aa2f7` + bold
- ✅ **Animated Feedback**: Rich spinners for MCP calls
- ✅ **Table Clarity**: Aligned columns, muted headers, readable rows
- ✅ **Responsive**: Graceful wrap/resize without breaking

---

## Preview Screenshots

(These are ASCII mockups; real implementation will use True Color)

### Screenshot 1: `chuzom status` (Proposed)
[See AFTER example in AREA 1 above]

### Screenshot 2: Session Summary (Proposed)
[See AFTER example in AREA 2 above]

### Screenshot 3: Live Routing (Proposed)
[See AFTER example in AREA 3 above]

---

## Next Steps

1. **User Review**: Does this design match your vision?
2. **Approve Roadmap**: Which phases first?
3. **Implementation**: Start with Phase 1 (foundation) in parallel branch
4. **Testing**: Ensure output parity before/after visually

Ready to build? 🚀
