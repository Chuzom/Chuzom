# v0.3.3 Modern TUI Redesign — Plan & Architecture

**Status**: Planning phase (v0.3.2 streaming complete)  
**Target Release**: After v0.3.2  
**Framework**: Textual (TUI framework) + Rich (formatting) + Plotext (charts)

---

## Vision

Transform Chuzom's CLI dashboards from static text output into an **interactive, real-time monitoring experience**. Users see live streaming feedback with transparent cost tracking and model selection visibility.

Key goals:
- 📊 **Real-time dashboards** with live metric updates
- 🎨 **Rich formatting** with colors, progress bars, and ASCII art
- 📈 **Inline charts** for cost trends and model performance
- ⌨️ **Interactive navigation** with keyboard shortcuts
- 🔄 **Session replay** capability (from streaming events)

---

## Architecture

### Components

#### 1. **Dashboard Container** (textual.widgets.Container)
The root layout organizing all sub-panels in a grid:
```
┌─────────────────────────────────────────────────────────┐
│ Chuzom Router v0.3.2 | Session: abc123 | $0.04 saved   │
├──────────────────────┬──────────────────────────────────┤
│ Route Timeline (L)   │ Live Output (R)                  │
│  ✓ Classification   │                                  │
│  ✓ Model Selected   │ Generated response text...       │
│  ✓ Attempting       │ (scrollable, real-time)          │
│  ✓ Committed ✨     │                                  │
├──────────────────────┼──────────────────────────────────┤
│ Metrics Summary (Bottom)                                │
│ ⏱️ Elapsed: 2.3s | 🤖 Model: claude-opus | 💰: $0.004 │
│ 📊 Tokens: 542→128 (↓0.2s/token) | 🎯 Confidence: 95%  │
└──────────────────────────────────────────────────────────┘
```

#### 2. **Timeline Panel** (Route Progress)
Displays streaming state transitions with elapsed time and icon indicators:
- `✓` (success) — Stage completed
- `⏳` (pending) — In progress
- `✗` (failed) — Stage failed (will retry)
- `✨` (committed) — Output started (commit barrier)

Stages shown:
1. **Routing** — Cost/profile resolution
2. **Classification** — Complexity detection (`complexity@confidence%`)
3. **Chain Built** — Models available in priority order
4. **Attempting** — Current model + attempt index
5. **Buffering** — Gates/judges active (if applicable)
6. **Committed** — First output visible ✨ (commit barrier marker)
7. **Complete** — Route finished

#### 3. **Live Output Panel** (Content Stream)
Real-time streaming of model output with:
- Syntax highlighting (code blocks with language detection)
- URL/ref detection (clickable regions)
- Thinking block extraction (collapsible Claude reasoning)
- Progressive rendering (word-by-word or line-by-line)

```
Generated Response:
────────────────────────────────────────────────
The answer is 42 because...

[Thinking Block (Claude)]
  <reasoning>
  The user asked about meaning of life, so 42 is the
  canonical reference from Douglas Adams...
  </reasoning>
```

#### 4. **Metrics Summary Bar** (Bottom)
Live KPI updates:
- ⏱️ **Elapsed**: Total wall-clock time
- 🤖 **Model**: Currently attempting model
- 💰 **Cost**: Real-time cost accumulation (from usage.final)
- 📊 **Throughput**: Tokens/sec (from output deltas)
- 🎯 **Confidence**: Classification confidence %
- 🔄 **Savings**: Estimated savings vs Opus

#### 5. **Cost Trend Chart** (Optional modal)
Press 'C' to toggle inline sparkline/bar chart showing:
```
Cost Trend (last 10 sessions)
$0.15 ┤     ╱╲
$0.10 ┤  ╱╲╱  ╲     ╱╲
$0.05 ┤╱╲╱    ╲╱╲╱╲╱
$0.00 ┴─────────────────
       Session #
```

---

## Interactive Features

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `↓`/`↑` | Scroll timeline / output |
| `C` | Toggle cost chart modal |
| `R` | Replay last session from events |
| `H` | Show help / legend |
| `Q` | Quit |
| `Space` | Pause/resume (freeze real-time updates) |

### Workflow

**While routing/streaming:**
1. User presses `chuzom route query "how does X work?" --watch`
2. Dashboard appears with empty timeline + live output area
3. Events stream in real-time, updating timeline milestones
4. Output panel updates character-by-character as deltas arrive
5. Metrics bar updates every usage.final event
6. On completion, dashboard freezes; user can:
   - Press `R` to replay (walk through events again)
   - Press `C` to see cost breakdown
   - Press `Q` to exit

**Cost dashboard (`chuzom summary --watch`):**
1. Displays aggregated metrics from lineage.db
2. Shows cost per complexity level
3. Sparkline trend chart (last 30 days)
4. Model frequency heatmap

---

## Implementation Phases

### Phase 1: Core TUI Scaffold (1 day)
- Set up Textual application structure
- Create basic layout (timeline + output + metrics)
- Hook streaming events to UI updates
- Test with mock streaming

### Phase 2: Rich Formatting (1 day)
- Color scheme and theming (Chuzom brand colors)
- Syntax highlighting for code output
- Icon/emoji integration (✓ ✗ ⏳ ✨)
- Thinking block collapsible sections

### Phase 3: Interactive Features (0.5 days)
- Keyboard handling (scroll, pause, replay)
- Modal dialogs (cost chart, help)
- Session replay from event log
- Help/legend display

### Phase 4: Polish & Testing (1 day)
- Error state handling
- Responsive resizing
- Performance optimization for large outputs
- Cross-platform terminal compatibility (macOS/Linux/Windows)

**Total estimate**: 3.5 days

---

## Data Flow

```
route_and_stream()
    ↓
Stream RouterStreamEvent objects
    ↓
TUI Event Handler (via listener)
    ↓
Timeline Panel: Extract type/model/status
Output Panel: Extract text from output.delta
Metrics Bar: Extract from usage.final
    ↓
Rich Formatting (colors, icons, sparklines)
    ↓
Textual Widget Tree (render)
    ↓
Terminal Display
```

---

## File Structure (v0.3.3)

```
src/chuzom/
├── tui/
│   ├── __init__.py
│   ├── app.py              # Main Textual application
│   ├── panels/
│   │   ├── timeline.py     # Route progress timeline
│   │   ├── output.py       # Live output stream display
│   │   ├── metrics.py      # KPI summary bar
│   │   └── chart.py        # Cost trend sparkline
│   ├── modals/
│   │   ├── help.py         # Help/legend
│   │   ├── cost_chart.py   # Cost trend modal
│   │   └── replay.py       # Session replay
│   └── theme.py            # Color scheme & styles

cli.py (updated)
├── main() → if --watch, use TUI app instead of text output
```

---

## Testing Strategy

**Unit Tests**:
- Panel data transformation (event → display text)
- Color/icon selection logic
- Chart rendering

**Integration Tests**:
- TUI app with mock streaming events
- Keyboard input handling
- Modal open/close state

**Manual Testing**:
- Real streaming via route_and_stream()
- Terminal size edge cases (small/large)
- Long outputs (scrolling)
- Cost accumulation accuracy

---

## Fallback Behavior

If Textual fails to load or is not installed:
```bash
$ chuzom route query "test" --watch
⚠️  Textual not installed. Falling back to classic output.
   Install with: pip install chuzom[tui]

(displays classic text-based output)
```

Optional dependency in pyproject.toml:
```toml
[project.optional-dependencies]
tui = [
    "textual>=0.80.0",
    "plotext>=5.2.0",
]
```

---

## v0.3.3 Release Checklist

- [ ] Core TUI scaffold with Textual app
- [ ] Timeline panel (route progress)
- [ ] Output panel (live streaming text)
- [ ] Metrics bar (KPIs)
- [ ] Rich formatting (colors, icons)
- [ ] Keyboard shortcuts (scroll, pause, help)
- [ ] Cost chart modal
- [ ] Session replay
- [ ] Error handling & edge cases
- [ ] Cross-platform testing
- [ ] Documentation + README update
- [ ] Optional dependency configuration
- [ ] Version bump (0.3.2 → 0.3.3)
- [ ] Tag & release to PyPI

---

## Future Enhancements (Post v0.3.3)

- 📱 **Mobile dashboard** (via web TUI or JSON API)
- 🔊 **Audio feedback** (completion bell, error beep)
- 🎬 **Recording** (save session as asciinema)
- 🌙 **Dark/light themes** (configurable)
- 📊 **Advanced analytics** (model comparison matrix, ROI calc)
- 🔗 **Integrations** (Slack notifications, data export)

---

## Design Philosophy

**Less is more**: Avoid information overload. Show only what's immediately relevant:
- During routing: timeline + output + live metrics
- After routing: cost breakdown + savings

**Graceful degradation**: Terminal too small? Stack vertically. Output too long? Paginate.

**Accessibility first**: Keyboard-only navigation, high contrast, clear status indicators.

---

## References

- **Textual**: https://textual.textualize.io
- **Rich**: https://rich.readthedocs.io
- **Plotext**: https://pypi.org/project/plotext/

---

**Created**: 2026-06-12  
**v0.3.2 Prerequisite**: Streaming integration (Phases A-D complete)  
**Owner**: yali.pollak@gmail.com
