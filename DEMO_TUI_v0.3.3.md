# Chuzom v0.3.3 TUI Dashboard — Live Demo

## Installation & Launch

```bash
# Install with TUI support
pip install chuzom[tui]

# Launch interactive dashboard
chuzom route query "How does photosynthesis work?" --watch
```

---

## Dashboard Layout

```
┌─ Chuzom Router v0.3.3 | Session: abc12345 | $0.0042 saved ─────────────────────────┐
├────────────────────────────────────┬──────────────────────────────────────────────────┤
│ 📋 Route Timeline                  │ 💬 Live Output                                   │
├────────────────────────────────────┤──────────────────────────────────────────────────┤
│                                    │                                                  │
│  ✓ Route Started                   │ Photosynthesis is the process by which plants   │
│    3 models available              │ convert light energy into chemical energy.       │
│                                    │                                                  │
│  ✓ Classification                  │ The light-dependent reactions occur in the      │
│    simple (98% confidence)          │ thylakoid membranes and involve:                │
│                                    │                                                  │
│  ✓ Model Selected                  │ 1. **Photon Absorption** — Chlorophyll absorbs  │
│    claude-3-haiku                   │    photons at 680nm and 700nm wavelengths      │
│                                    │                                                  │
│  ✓ Attempting (Attempt 1)          │ 2. **Water Splitting** — H₂O → 2H⁺ + ½O₂ + 2e⁻ │
│    claude-3-haiku                   │                                                  │
│                                    │ 3. **ATP Generation** — ADP + Pi → ATP          │
│  ✓ Committed ✨                     │                                                  │
│    Output started (no fallback)     │ [Thinking Block] (Claude - collapsible)        │
│                                    │ ╭─────────────────────────────────────────────╮  │
│  ✓ Complete                        │ │ 🧠 Analyzing question depth...              │  │
│    Final model: claude-3-haiku      │ │ Selecting detailed scientific explanation   │  │
│                                    │ ╰─────────────────────────────────────────────╯  │
│                                    │                                                  │
│                                    │ The Calvin Cycle (light-independent reactions)  │
│                                    │ in the stroma produces glucose molecules...     │
│                                    │                                                  │
├────────────────────────────────────┼──────────────────────────────────────────────────┤
│ 📈 Metrics                         │ Quick Actions                                    │
├────────────────────────────────────┼──────────────────────────────────────────────────┤
│ 🤖 Model      : claude-3-haiku     │ [💾 Save Session] [📊 Cost Breakdown]          │
│ 📊 Tokens     : 486                │ [🔄 Session History]                           │
│ 📥 Input      : 125                │                                                  │
│ 📤 Output     : 361                │                                                  │
│ 💰 Cost       : $0.00042           │                                                  │
│ ⏱️  Latency    : 2341ms            │                                                  │
│ 🚀 Throughput : 154 tok/s          │                                                  │
└────────────────────────────────────┴──────────────────────────────────────────────────┘
```

---

## Interactive Walkthrough

### **Phase 1: Routing Started**
```
Timeline shows:
  ✓ Route Started (3 candidates)

Output shows:
  (empty - waiting for model selection)

Metrics:
  All at 0
```

### **Phase 2: Classification & Model Selection**
```
Timeline shows:
  ✓ Route Started
  ✓ Classification → "simple (98%)"
  ✓ Model Selected → "claude-3-haiku"

Output:
  (still waiting)

Metrics:
  Model: claude-3-haiku
```

### **Phase 3: Attempting**
```
Timeline shows:
  ✓ Route Started
  ✓ Classification
  ✓ Model Selected
  ⏳ Attempting (Attempt 1)

Output:
  (streaming hasn't started yet)

Metrics:
  Waiting...
```

### **Phase 4: Committed (Output Starts) ✨**
```
Timeline shows:
  ✓ Route Started
  ✓ Classification
  ✓ Model Selected
  ✓ Attempting
  ✓ Committed ✨ (THIS IS THE COMMIT BARRIER)
  
Output:
  "Photosynthesis is the process by which plants..."
  (streaming real-time character by character)

Metrics:
  Tokens: 1 (growing in real-time)
  Throughput: 123 tok/s
  Cost: $0.00001
```

### **Phase 5: Streaming Content**
```
Timeline:
  (all previous stages locked)
  ✓ Committed ✨ (frozen - NO FALLBACK POSSIBLE)

Output:
  "Photosynthesis is the process by which plants convert 
   light energy into chemical energy through a series of 
   complex biochemical reactions..."
  
  [Thinking Block - Claude] (collapsible)
  ╭─────────────────────────────────────────╮
  │ 🧠 The user asked about photosynthesis, │
  │ so I should provide a detailed but      │
  │ understandable scientific explanation   │
  │ suitable for educational purposes.      │
  ╰─────────────────────────────────────────╯

Metrics (LIVE UPDATE):
  📊 Tokens: 189 ↑
  💰 Cost: $0.00025 ↑
  🚀 Throughput: 145 tok/s
```

### **Phase 6: Complete**
```
Timeline:
  ✓ Route Started
  ✓ Classification
  ✓ Model Selected
  ✓ Attempting
  ✓ Committed ✨
  ✓ Complete
    Final model: claude-3-haiku

Output:
  (full response visible)

Metrics (FINAL):
  🤖 Model: claude-3-haiku
  📊 Tokens: 486 (361 output)
  💰 Cost: $0.00042
  ⏱️  Latency: 2341ms
  🚀 Throughput: 154 tok/s
```

---

## Keyboard Shortcuts (Interactive)

### While Running:
```
↓/↑     Scroll through output or timeline
Space   Pause/resume streaming output
H       Show help legend
Q       Quit dashboard
```

### After Complete:
```
C       Show Cost Breakdown Chart:
        ┌─────────────────────────────┐
        │ Cost Trend (Last 10 Routes) │
        │ $0.10 ┤  ╱╲                 │
        │ $0.05 ┤╱  ╲  ╱╲             │
        │ $0.00 ┴──────────────       │
        └─────────────────────────────┘

R       Replay Session from Events:
        (Re-streams the entire routing sequence
         at 1x, 2x, or 4x speed)
        
        Press SPACE to pause/resume replay
        Press ← → to step through events
        
H       Show Help:
        ╭────────────────────────────────╮
        │ Chuzom TUI v0.3.3 - Help       │
        │                                │
        │ ↓/↑  Scroll                    │
        │ C    Cost chart                │
        │ R    Replay session            │
        │ H    Help                      │
        │ Q    Quit                      │
        │                                │
        │ Cost Savings: $0.0042          │
        │ vs. Opus: -99% ($0.28 saved)   │
        ╰────────────────────────────────╯

Q       Exit dashboard
```

---

## Features Demonstrated

### ✅ Real-time Streaming
- Character-by-character output update
- Metrics update every 100ms
- No buffering - immediate display

### ✅ Commit Barrier
- Timeline shows "✓ Committed ✨" 
- After this point, NO fallback possible
- Safety invariant visually enforced

### ✅ Thinking Block Extraction
- Claude thinking blocks highlighted
- Collapsible for readability
- Shows model's reasoning process

### ✅ Cost Tracking
- Live cost accumulation
- Tokens counted in real-time
- Throughput displayed

### ✅ Session Replay
- Press R to walk through routing again
- All events from this session stored
- Replay at variable speed

### ✅ Responsive Layout
- Works on terminals 80 cols wide
- Stacks panels vertically if needed
- Full keyboard navigation

---

## Fallback Behavior

**If Textual not installed:**
```bash
$ chuzom route query "test" --watch
⚠️  Textual not installed. Falling back to classic output.
   Install with: pip install chuzom[tui]

============================================================
RESPONSE
============================================================
[text output here]

============================================================
METRICS
============================================================
Model: claude-3-haiku
Tokens: 125 → 361
Cost: $0.00042
Latency: 2341.5ms
============================================================
```

---

## Version Information

- **v0.3.3**: Modern TUI Dashboard (Textual Framework)
- **v0.3.2**: Streaming Integration (underlying layer)
- **Framework**: Textual 0.80+ with Rich formatting
- **Optional Deps**: `pip install chuzom[tui]`

---

## Code Structure

```
src/chuzom/tui/
├── __init__.py          (14 lines)  → Exports ChuzomDashboard
├── app.py              (331 lines) → Main Textual application
├── panels.py           (226 lines) → Timeline, Output, Metrics widgets
├── messages.py         (102 lines) → Message types for communication
├── cli.py               (86 lines) → CLI integration
└── dashboard.css       (175 lines) → Layout & styling
```

---

## Production Readiness

✅ All components implemented  
✅ Message-driven architecture  
✅ Reactive state management  
✅ Graceful fallback if TUI unavailable  
✅ Keyboard navigation complete  
✅ CSS styling responsive  
✅ Panel components modular  
✅ CLI integration ready  

**Status**: Ready to use with `pip install chuzom[tui]`

---

Created: 2026-06-12 | Version: v0.3.3 | Framework: Textual 0.80+
