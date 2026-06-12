# Chuzom Routing Hang Diagnosis

## Issue
When routing decision is `llm_code` (or other MCP tools), the tool call hangs indefinitely with:
- ✗ No timeout message
- ✗ No error feedback  
- ✗ No progress indicator
- = User sees "Honking..." spinner forever

## Evidence from Logs

### auto-route-debug.log (18:51 - 18:57)
```
[18:51:05] INVOCATION START ID=1781286665.767 prompt_len=32
[18:51:05] OUTPUTTING: tool=llm_code task=code/moderate method=code-context-inherit
[18:51:05] OUTPUT COMPLETE

[18:57:00] INVOCATION START ID=1781287020.279 prompt_len=262
[18:57:00] OUTPUTTING: tool=llm_code task=code/moderate method=heuristic  
[18:57:00] OUTPUT COMPLETE
```

✓ Hook successfully decides routing
✓ Hook outputs decision to Claude Code
✓ Hook completes normally

### enforcement.log (same timestamps)
```
[2026-06-12 18:51:05] NO_ROUTE session=a084a374-2ee expected=llm_code task=code/moderate
[2026-06-12 18:57:00] NO_ROUTE session=a084a374-2ee expected=llm_code task=code/moderate
```

✗ Tool invocation never happens
✗ Expected tool `llm_code` was not called
✗ PreToolUse hook never fires or fails silently

## The Disconnect

```
┌─────────────────────────────────────────┐
│ UserPromptSubmit Hook (auto-route.py)  │
│  ✓ Classifies task                      │
│  ✓ Decides: use llm_code                │
│  ✓ Outputs to Claude Code               │
│  ✓ Returns successfully                 │
└──────────────┬──────────────────────────┘
               │ "Route to llm_code"
               ↓
┌──────────────────────────────────────────┐
│ Claude Code Tool Invocation Layer         │
│  ✗ MCP server call timeout or hangs      │
│  ✗ No response from mcp__chuzom__llm_code│
│  ✗ No timeout/error message sent back    │
│  = User stares at spinning wheel         │
└──────────────────────────────────────────┘
```

## Possible Root Causes

1. **MCP Server Down/Unresponsive**
   - `chuzom` MCP server not running
   - Server crashed silently
   - Check: `ps aux | grep chuzom`

2. **Tool Timeout**
   - LLM API call hanging (OpenAI/Gemini timeout)
   - No response from provider
   - Default timeout not enforced

3. **Network/IPC Issue**
   - Claude Code ↔ MCP server communication broken
   - Socket/pipe timeout
   - Check: `chuzom doctor`

4. **Tool Registration Issue**
   - Tool not properly registered in MCP
   - Tool called with wrong parameters
   - Check: `.mcp.json` configuration

5. **PreToolUse Hook Blocking**
   - `chuzom-enforce-route.py` hook rejects the call
   - No error returned to user
   - Silent failure

## Reproduction Steps

To reproduce and diagnose:

1. **Open new Claude Code session**
2. **Ask a code-moderate task**: "Redesign the Live Routing Feedback UI component. Build three TUI components..."
3. **Observe**:
   - Does it route? (check for ⚡ chuzom → model indicator)
   - Does it hang? (after 10s, shows "Honking...")
   - Check logs: `tail -f ~/.chuzom/enforcement.log`

4. **Diagnose in parallel**:
   - Check MCP: `chuzom doctor`
   - Check logs: `tail -f ~/.chuzom/auto-route-debug.log`
   - Monitor: `ps aux | grep chuzom`

## The Real Problem: No Feedback

Even if we fix the hang, the USER NEVER KNEW IT WAS HANGING.

Solution: Add timeout + status message:

```
⚡ Classifying...  [████░░░░░░] 35%  ~2.3s
[after 10s]
⚠  Tool call timeout (10s) — fallback to direct mode
→ Routing to claude-opus (fallback)
```

## Recommended Fixes

### Short-term (Fix the Hang)
1. Ensure MCP server is running
2. Add timeout to tool invocation (10s max)
3. Display error if timeout occurs

### Medium-term (Better Feedback)
1. Implement status_spinner (already built in UI components!)
2. Show progress: "Classifying... Routing... Complete"
3. Timeout message with fallback option

### Long-term (Resilience)
1. Implement circuit breaker for hung tools
2. Automatic fallback to direct Claude on timeout
3. User dashboard showing tool health
4. Instrumentation/observability for tool calls

## Files to Investigate

- `~/.chuzom/enforcement.log` — Tool invocation records
- `~/.chuzom/auto-route-debug.log` — Routing decisions
- `chuzom doctor` — System health
- `src/chuzom/hooks/chuzom-enforce-route.py` — PreToolUse hook
- `src/chuzom/server.py` — MCP server impl

## Immediate Action

Run `chuzom doctor` to see MCP server health:
```bash
chuzom doctor
```

Look for:
- ✓ MCP server registered
- ✓ Ollama running (classifier)
- ✓ Provider keys set
- ✗ Any warnings/errors
