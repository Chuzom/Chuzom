# v0.3.3 TUI Dashboard — Quick Start & Visual Guide

## Quick Start

```bash
# 1. Install Chuzom with TUI support
pip install chuzom[tui]

# 2. Launch dashboard for a routing task
chuzom route query "What is machine learning?" --watch

# 3. Watch the dashboard in real-time!
```

---

## What You'll See (Step-by-Step)

### **Second 0: Dashboard launches**

```
┌─ Chuzom Router v0.3.3 | Session: Loading... ─────────────┐
│                                                             │
│  [Waiting for routing to begin...]                         │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### **Second 0-1: Route starts (classification)**

```
┌─ Chuzom Router v0.3.3 | Session: 8a4f9c2e | $0 saved ─────┐
├─────────────────────────────┬───────────────────────────────┤
│ 📋 Route Timeline           │ 💬 Live Output                │
│                             │                               │
│ ✓ Route Started             │ (Waiting for model output...) │
│   3 models available        │                               │
│                             │                               │
│ ✓ Classification            │                               │
│   simple (95% confidence)   │                               │
│                             │                               │
│ ⏳ Model Selection           │                               │
│   haiku > sonnet > opus     │                               │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 📈 Metrics                  │                               │
│ 🤖 Model: N/A               │                               │
│ 📊 Tokens: 0                │                               │
│ 💰 Cost: $0.0000            │                               │
└─────────────────────────────┴───────────────────────────────┘
```

### **Second 1-2: Model selected & attempting**

```
┌─ Chuzom Router v0.3.3 | Session: 8a4f9c2e | $0 saved ─────┐
├─────────────────────────────┬───────────────────────────────┤
│ 📋 Route Timeline           │ 💬 Live Output                │
│                             │                               │
│ ✓ Route Started             │ (Model buffering output...)   │
│   3 models available        │                               │
│                             │                               │
│ ✓ Classification            │                               │
│   simple (95% confidence)   │                               │
│                             │                               │
│ ✓ Model Selected            │                               │
│   claude-3-haiku            │                               │
│                             │                               │
│ ⏳ Attempting (Attempt 1)    │                               │
│   claude-3-haiku            │                               │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 📈 Metrics                  │                               │
│ 🤖 Model: claude-3-haiku    │                               │
│ 📊 Tokens: 0 (buffering)    │                               │
│ 💰 Cost: $0.0000            │                               │
└─────────────────────────────┴───────────────────────────────┘
```

### **Second 2-3: Output starts! (Commit Barrier ✨)**

```
┌─ Chuzom Router v0.3.3 | Session: 8a4f9c2e | $0.00008 ─────┐
├─────────────────────────────┬───────────────────────────────┤
│ 📋 Route Timeline           │ 💬 Live Output                │
│                             │                               │
│ ✓ Route Started             │ Machine learning is a subset │
│   3 models available        │ of artificial intelligence    │
│                             │ that enables systems to       │
│ ✓ Classification            │ learn and improve from        │
│   simple (95%)              │ experience without being      │
│                             │ explicitly programmed.       │
│ ✓ Model Selected            │                               │
│   claude-3-haiku            │ [Thinking Block - Claude] ▼   │
│                             │                               │
│ ✓ Attempting                │                               │
│   Committed ✨ (BARRIER ON) │                               │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 📈 Metrics                  │                               │
│ 🤖 Model: claude-3-haiku    │                               │
│ 📊 Tokens: 48               │                               │
│ 💰 Cost: $0.00008           │                               │
│ 🚀 Throughput: 160 tok/s    │                               │
└─────────────────────────────┴───────────────────────────────┘
```

### **Second 3-5: Streaming continues**

```
┌─ Chuzom Router v0.3.3 | Session: 8a4f9c2e | $0.00032 ─────┐
├─────────────────────────────┬───────────────────────────────┤
│ 📋 Route Timeline           │ 💬 Live Output                │
│                             │                               │
│ ✓ Route Started             │ Machine learning is a subset │
│   3 models available        │ of artificial intelligence    │
│                             │ that enables systems to learn │
│ ✓ Classification            │ and improve from experience   │
│   simple (95%)              │ without being explicitly      │
│                             │ programmed.                   │
│ ✓ Model Selected            │                               │
│   claude-3-haiku            │ Key Types:                    │
│                             │ • Supervised Learning         │
│ ✓ Attempting                │ • Unsupervised Learning       │
│   Committed ✨              │ • Reinforcement Learning      │
│                             │                               │
│ ⏳ Streaming...             │ Applications:                 │
│   188 tokens received       │ • Computer vision             │
│                             │ • Natural language            │
│                             │ • Recommendation systems      │
│                             │ • Autonomous vehicles         │
│                             │                               │
│                             │ [Thinking Block - Claude] ▼   │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 📈 Metrics                  │                               │
│ 🤖 Model: claude-3-haiku    │                               │
│ 📊 Tokens: 188              │                               │
│ 💰 Cost: $0.00032           │                               │
│ 🚀 Throughput: 142 tok/s    │                               │
│ ⏱️  Elapsed: 1.32s           │                               │
└─────────────────────────────┴───────────────────────────────┘
```

### **Second 5+: Complete**

```
┌─ Chuzom Router v0.3.3 | Session: 8a4f9c2e | $0.00042 ─────┐
├─────────────────────────────┬───────────────────────────────┤
│ 📋 Route Timeline           │ 💬 Live Output                │
│                             │                               │
│ ✓ Route Started             │ Machine learning is a subset │
│   3 models available        │ of artificial intelligence    │
│                             │ that enables systems to learn │
│ ✓ Classification            │ and improve from experience   │
│   simple (95%)              │ without being explicitly      │
│                             │ programmed.                   │
│ ✓ Model Selected            │                               │
│   claude-3-haiku            │ Key Types:                    │
│                             │ • Supervised Learning         │
│ ✓ Attempting                │ • Unsupervised Learning       │
│   Committed ✨              │ • Reinforcement Learning      │
│                             │                               │
│ ✓ Complete                  │ Applications:                 │
│   Final: claude-3-haiku     │ • Computer vision             │
│                             │ • Natural language processing │
│                             │ • Recommendation systems      │
│                             │ • Autonomous vehicles         │
│                             │ • Predictive analytics        │
│                             │                               │
│                             │ Machine learning algorithms   │
│                             │ learn from data patterns and  │
│                             │ make predictions based on     │
│                             │ those patterns...             │
│                             │                               │
│                             │ [Thinking Block - Claude] ▲   │
│                             │                               │
├─────────────────────────────┼───────────────────────────────┤
│ 📈 Metrics (FINAL)          │ Quick Actions                 │
│ 🤖 Model: claude-3-haiku    │ [💾 Save] [📊 Cost] [🔄 Hist]│
│ 📊 Tokens: 312 (input: 18)  │                               │
│ 💰 Cost: $0.00042           │ Press C for Cost Chart        │
│ ⏱️  Latency: 2187ms          │ Press R to Replay Session     │
│ 🚀 Throughput: 143 tok/s    │ Press H for Help              │
│ 🎯 Confidence: 95%          │                               │
└─────────────────────────────┴───────────────────────────────┘
```

---

## Interactive Features (Live Demo)

### **Press 'C' — View Cost Breakdown Chart**

```
╭──────────────────────────────────╮
│ 💰 Cost Analysis                 │
├──────────────────────────────────┤
│                                  │
│ Session Cost:  $0.00042          │
│ vs. Opus:      $0.28             │
│ Savings:       $0.27958 (-99.9%) │
│                                  │
│ Token Cost Breakdown:            │
│ Input (18):    $0.000018         │
│ Output (312):  $0.000402         │
│                                  │
│ Cost Trend (Last 10 Routes):     │
│                                  │
│ $0.40 ┤                          │
│ $0.30 ┤    ╱╲                   │
│ $0.20 ┤   ╱  ╲  ╱╲             │
│ $0.10 ┤  ╱    ╲╱  ╲           │
│ $0.00 ┴───────────────         │
│        1  2  3  4  5  6  7  8   │
│                                  │
│ [ESC to close]                   │
╰──────────────────────────────────╯
```

### **Press 'R' — Replay Session from Events**

```
╭──────────────────────────────────╮
│ 🔄 Session Replay                │
├──────────────────────────────────┤
│                                  │
│ Session: 8a4f9c2e                │
│ Events: 12 total                 │
│                                  │
│ Replay Speed:  1x [▓▓▓░░░░░░░░] │
│ (Use ← → to adjust)              │
│                                  │
│ Progress:     █████░░░░░░░░░░░░ │
│ Events: 6/12 (50%)               │
│                                  │
│ Current Event:                   │
│ ✓ Attempting (Attempt 1)         │
│   claude-3-haiku                 │
│   Timestamp: +1.243s             │
│                                  │
│ [SPACE] Pause  [R] Resume        │
│ [→] Next Event  [←] Prev Event   │
│ [ESC] Close                      │
╰──────────────────────────────────╯
```

### **Press 'H' — Show Help**

```
╭──────────────────────────────────╮
│ 📖 Help & Keyboard Shortcuts     │
├──────────────────────────────────┤
│                                  │
│ NAVIGATION:                      │
│   ↓    Scroll output down        │
│   ↑    Scroll output up          │
│                                  │
│ FEATURES:                        │
│   C    Show cost chart           │
│   R    Replay session            │
│   H    Show this help            │
│                                  │
│ CONTROL:                         │
│   Space   Pause/resume streaming │
│   Q       Quit dashboard         │
│                                  │
│ ABOUT:                           │
│   Chuzom v0.3.3 TUI Dashboard    │
│   Framework: Textual 0.80+       │
│   Docs: github.com/ypollak2/     │
│         chuzom                   │
│                                  │
│ [ESC to close]                   │
╰──────────────────────────────────╯
```

---

## Testing the TUI Locally

### **Option 1: Run with real routing (requires API keys)**

```bash
# Install with TUI
pip install chuzom[tui]

# Run with real Claude API
export ANTHROPIC_API_KEY="sk-ant-..."
chuzom route query "Explain quantum computing" --watch
```

### **Option 2: Mock test (no API keys needed)**

```bash
# Create a test script
cat > test_tui.py << 'EOF'
import asyncio
from chuzom.tui.app import ChuzomDashboard
from chuzom.tui.messages import StreamEventMessage

async def mock_streaming_events():
    """Yield mock streaming events for testing."""
    events = [
        {
            "seq": 1,
            "type": "route.started",
            "correlation_id": "test123",
            "ts_monotonic_ms": 0,
            "task_type": "query",
            "profile": "BUDGET",
            "complexity": "simple",
            "candidate_count": 3,
            "chain_preview": ["model1", "model2"],
            "buffered_mode": False,
        },
        {
            "seq": 2,
            "type": "attempt.started",
            "correlation_id": "test123",
            "ts_monotonic_ms": 100,
            "attempt_index": 1,
            "model": "claude-3-haiku",
            "provider": "anthropic",
            "emergency_fallback": False,
        },
        {
            "seq": 3,
            "type": "attempt.committed",
            "correlation_id": "test123",
            "ts_monotonic_ms": 200,
            "attempt_index": 1,
            "model": "claude-3-haiku",
            "visible_output_started": True,
        },
        {
            "seq": 4,
            "type": "output.delta",
            "correlation_id": "test123",
            "ts_monotonic_ms": 300,
            "attempt_index": 1,
            "model": "claude-3-haiku",
            "text": "Hello from the TUI dashboard! ",
            "chars": 31,
            "approx_tokens": 8,
        },
        {
            "seq": 5,
            "type": "usage.final",
            "correlation_id": "test123",
            "ts_monotonic_ms": 2500,
            "model": "claude-3-haiku",
            "provider": "anthropic",
            "input_tokens": 50,
            "output_tokens": 8,
            "cost_usd": 0.00009,
            "latency_ms": 2400.0,
        },
        {
            "seq": 6,
            "type": "route.completed",
            "correlation_id": "test123",
            "ts_monotonic_ms": 2600,
            "final_model": "claude-3-haiku",
            "final_provider": "anthropic",
            "chain_attempts": ["claude-3-haiku"],
            "used_emergency_fallback": False,
            "cached": False,
        },
    ]
    
    for event in events:
        await asyncio.sleep(0.5)  # Simulate delay
        yield event

# Run the app with mock events
app = ChuzomDashboard()

async def run_with_mocks():
    async with app.run_test() as pilot:
        async for event in mock_streaming_events():
            app.post_message(StreamEventMessage(event))
            await asyncio.sleep(0.1)

asyncio.run(run_with_mocks())
EOF

# Run the test
uv run python test_tui.py
```

---

## What Makes This v0.3.3

✅ **Real-time streaming visualization**  
✅ **Commit barrier visually marked (✨)**  
✅ **Session replay from events**  
✅ **Interactive keyboard navigation**  
✅ **Cost tracking with charts**  
✅ **Thinking block extraction**  
✅ **Responsive layout for any terminal size**  
✅ **Graceful fallback if Textual unavailable**  

---

## Production Deployment

```bash
# Install globally
pip install chuzom[tui]

# Or with specific version
pip install chuzom[tui]==0.3.3

# For development/testing
pip install -e ".[tui]"
```

---

**Status**: v0.3.3 TUI Dashboard is production-ready! 🚀

Run it now with: `chuzom route query "test" --watch`
