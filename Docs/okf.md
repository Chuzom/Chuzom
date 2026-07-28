# Open Knowledge Format (OKF) Integration

Chuzom integrates with the [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) —
a vendor-neutral standard for representing knowledge as plain markdown files with YAML
frontmatter. Your local bundle lives at `~/.chuzom/knowledge/` and grows automatically
as you work.

## How it works

Three features work together.

### 1. Context injection

Before routing any task, chuzom scans `~/.chuzom/knowledge/` for concept docs whose
content overlaps with your prompt (keyword scoring). The top matches are prepended as a
`<knowledge_context>` block. A prompt asking about `router.py` routing logic will arrive
at Gemini Flash pre-loaded with the relevant module doc — no extra cost, no manual work.

### 2. Model Capability Catalog

`~/.chuzom/knowledge/models/*.md` holds one OKF concept per model, describing strengths,
weaknesses, p50 latency, and fallback hints. Seeded automatically on first run:

| File | Model |
|---|---|
| `gemini-2.5-flash.md` | Fast/cheap; best for refactoring and summarization |
| `gemini-2.5-pro.md` | Higher quality; use for architecture and complex analysis |
| `gpt-5.5.md` | Codex CLI; strong at multi-step reasoning |
| `gpt-5.4.md` | Premium Codex; deepest reasoning, highest latency |

Edit any file to tune how models describe themselves to each other. Add a new file to
introduce a new model — no code change required.

### 3. Side-effect enrichment

After every successful routing call, a background task extracts file paths and
function/class names from the prompt and response, then writes a `SourceFile` concept doc:

```
~/.chuzom/knowledge/source/src/chuzom/router.py.md
  type: SourceFile
  key_symbols: [route_and_call, _dispatch_model_loop]
  last_model: gemini-2.5-flash
```

The first call that touches a file records what it learned. Every subsequent call on
that file gets that knowledge injected — for free.

## The compounding loop

```
routing call → enrich (write SourceFile doc)
             → next call finds it → inject as context
             → cheap model succeeds → fewer fallbacks
             → saves more → next call enriches more
```

The bundle builds itself. The more chuzom is used on a codebase, the less it needs to
escalate to expensive models.

## Extending the bundle

Any markdown file with YAML frontmatter dropped into `~/.chuzom/knowledge/` is
automatically indexed:

```markdown
---
type: TeamConvention
title: Error handling policy
tags: [errors, python, conventions]
description: How this codebase handles exceptions
---

All errors must be caught at route boundaries. Never use bare `except Exception`.
Custom exceptions inherit from `DomainError`.
```

Chuzom refreshes the bundle every 60 seconds, so new files are picked up without a
restart.

## Bundle structure

```
~/.chuzom/knowledge/
├── models/                     # Model Capability Catalog (auto-seeded)
│   ├── gemini-2.5-flash.md
│   ├── gemini-2.5-pro.md
│   ├── gpt-5.5.md
│   └── gpt-5.4.md
├── source/                     # SourceFile concepts (auto-written)
│   └── src/chuzom/
│       ├── router.py.md
│       └── okf.py.md
└── <your-concepts>/            # Anything you add manually
    ├── team-conventions.md
    └── architecture.md
```
