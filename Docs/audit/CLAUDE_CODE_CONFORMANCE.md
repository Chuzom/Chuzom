# Claude Code Conformance Audit — Input Document

> **RESOLUTION (post-audit):** The two verified findings were fixed in the same
> commit that adds this doc:
> - **P0** — `enforce-route.py` now emits `hookSpecificOutput.permissionDecision="deny"`
>   (+ `permissionDecisionReason`) alongside the legacy `decision:block`, so blocking
>   uses the current documented PreToolUse contract and no longer depends on the
>   deprecated compat shim. Locked by `test_block_output_carries_permission_decision_p0`.
> - **P1** — `auto-route.py::_normalize_output_for_platform` now renames
>   `contextForAgent`→`additionalContext` for ALL platforms (incl. Claude Code), so the
>   two early-exit hint paths inject context via the documented field. Locked by
>   `tests/test_cc_conformance_p1.py`.
>
> Line numbers below are the audit-date snapshot and have since shifted by the fixes.
> The remaining P1 (`install_hooks` settings.json MCP write) and P2 items stand as
> input for the formal audit.

**Purpose:** Verify Chuzom's Claude Code hook/MCP/settings integration against the
CURRENT official Claude Code docs (fetched live from `code.claude.com/docs` on this
audit date) and flag every drift/deprecation. This is an INPUT to a later formal
audit, not the audit itself. No Chuzom source was modified to produce this report.

**Docs fetched (raw markdown, this session):**
- `https://code.claude.com/docs/en/hooks.md` (3173 lines)
- `https://code.claude.com/docs/en/settings.md` (1214 lines)
- `https://code.claude.com/docs/en/mcp.md` (1282 lines)
- `https://code.claude.com/docs/en/permissions.md`
- `https://code.claude.com/docs/en/tools-reference.md`

No version banner/date was printed on the pages themselves; version gates embedded
in the text (e.g. "Requires Claude Code v2.1.208 or later") are the only dating
signal available and are quoted below where relevant. **A formal audit must record
the installed `claude --version` and diff behavior against these version gates.**

**Chuzom files reviewed:**
- `src/chuzom/hooks/auto-route.py` (UserPromptSubmit, 3691 lines)
- `src/chuzom/hooks/enforce-route.py` (PreToolUse, ~1460 lines)
- `src/chuzom/hooks/session-start.py` (SessionStart)
- `src/chuzom/hooks/stop-enforce.py` (Stop)
- `src/chuzom/hooks/response_formatter.py` (shared output-builder helpers)
- `src/chuzom/install_hooks.py` (settings.json + MCP registration writer)

---

## 1. Findings — Hook Output Contracts

### 1.1 DEPRECATED — `enforce-route.py` PreToolUse block uses the legacy top-level `decision`/`reason` field

- **Chuzom code:** `src/chuzom/hooks/enforce-route.py:1479`
  ```python
  json.dump({"decision": "block", "reason": block_reason}, sys.stdout)
  ```
  This is the **only** JSON-emitting statement in the entire file — i.e. every
  PreToolUse block Chuzom ever issues goes through this line. No `sys.exit(2)` is
  called afterward either (`main()` falls off the end → exit code 0).

- **Current docs contract** (`hooks.md:1581-1583`, verbatim):
  > PreToolUse previously used top-level `decision` and `reason` fields, but these
  > are deprecated for this event. Use `hookSpecificOutput.permissionDecision` and
  > `hookSpecificOutput.permissionDecisionReason` instead. The deprecated values
  > `"approve"` and `"block"` map to `"allow"` and `"deny"` respectively. Other
  > events like PostToolUse and Stop continue to use top-level `decision` and
  > `reason` as their current format.

  Decision-control table (`hooks.md:1544-1553`): PreToolUse's *only* documented
  live field is `hookSpecificOutput.permissionDecision` (`allow`/`deny`/`ask`/`defer`)
  + `hookSpecificOutput.permissionDecisionReason` + `updatedInput` + `additionalContext`.

- **Verdict:** **DEPRECATED, currently working via back-compat shim.** The docs
  explicitly say the deprecated value still maps (`"block"` → `"deny"`), so this is
  not yet a silent no-op. But it is compat-shim behavior Anthropic could remove in
  a future major version without further notice (deprecated ≠ permanently
  supported), and it forfeits the richer PreToolUse-only capabilities: `"ask"`
  (audit trail via visible permission prompt with a `[Local]`/`[Plugin]` source
  label), `"defer"` (needed for the Agent-SDK/`-p` resume flow), and `updatedInput`
  (rewrite `tool_input` instead of just deny — e.g. Chuzom could auto-append a
  read-only flag to a Bash command instead of hard-blocking it).
- **Consequence if the shim is ever removed:** every PreToolUse block in
  `enforce-route.py` becomes a **silent no-op** — the tool call proceeds
  unblocked, `hard`/`smart` enforcement mode stops enforcing anything, and nothing
  in Chuzom's own logs would show a difference (the hook still runs, still logs
  `_log_violation(...)`, still writes to `enforcement.log` — only the actual block
  effect disappears). This is the single highest-impact drift in this repo's
  Claude Code integration because it is currently invisible.
- **P0.**

### 1.2 DRIFT (likely bug) — `auto-route.py` emits an undocumented `hookSpecificOutput.contextForAgent` field for real Claude Code sessions

- **Chuzom code:**
  - `src/chuzom/hooks/auto-route.py:2606-2650` — `_normalize_output_for_platform()`.
    Comment (verbatim, lines 2606-2611):
    ```
    # ─── v9.3.0: Platform detection for Codex CLI vs Claude Code ─────────────────
    # Codex CLI's UserPromptSubmit hook output schema ONLY supports
    # `additionalContext` — emitting `contextForAgent` is rejected (schema is
    # additionalProperties: false). Claude Code prefers `contextForAgent` for
    # higher-priority directives but accepts both. So we detect platform from
    # hook_input["model"] and normalize the output key just-in-time.
    ```
    The function only renames `contextForAgent` → `additionalContext` when
    `_is_codex_session()` or `_is_gemini_session()` is true (lines 2645-2646). For
    a genuine Claude Code session (the majority case — neither Codex nor Gemini),
    the key is left as `contextForAgent`.
  - Two live early-exit paths emit `contextForAgent` and are **not** the main
    routing-directive path, so they hit this bug on every real Claude Code
    invocation that takes them:
    - `auto-route.py:2781-2796` — the "sidecar pre-executed" fast path.
    - `auto-route.py:2839-2854` — the "MCP capability hint" fast path.
  - Contrast with the **primary** routing-directive emission at
    `auto-route.py:3645-3650`, which correctly uses `additionalContext` directly
    (not `contextForAgent`) — so the main `⚡ MANDATORY ROUTE:` injection is fine;
    only the two secondary hint paths are affected.

- **Current docs contract:** `hooks.md` documents exactly one context-injection
  field name for UserPromptSubmit's `hookSpecificOutput`: **`additionalContext`**
  (`hooks.md:1177-1210`, and the universal `additionalContext` semantics at
  `hooks.md` "Add context for Claude"). `contextForAgent` does not appear
  **anywhere** in the fetched `hooks.md` (0 matches; `additionalContext` appears
  40 times). It is not a documented Claude Code field for any event.

- **Verdict:** **DRIFT — code comment's premise ("Claude Code prefers
  `contextForAgent`") does not match current docs.** Unknown fields inside
  `hookSpecificOutput` are, per every documented example, simply additional keys
  Claude Code doesn't look for — there is no evidence Claude Code reads
  `contextForAgent` at all. If that's correct, the sidecar-preexec hint and the
  MCP-capability hint are **silently dropped for native Claude Code users** (the
  platform's primary/majority user base) while working correctly only for the
  minority Codex/Gemini pull-integration paths, which is the *opposite* of the
  comment's stated intent ("Claude Code prefers contextForAgent for
  higher-priority directives").
- **Consequence:** two specific UX features (sidecar fast-path data injection,
  MCP-server routing hints) are dead code for real Claude Code sessions. Low
  severity (advisory hints, not enforcement) but easy to fix and should be
  reconciled with 1.1's more severe finding using the same review pass.
- **P1** — verify empirically on a live install (does Claude Code actually ignore
  unknown `hookSpecificOutput` keys, or does it error/warn?); if confirmed, this
  is a one-line fix (drop the Codex/Gemini gate, always emit `additionalContext`).

### 1.3 UNVERIFIABLE — `response_formatter.build_echo_output()` sets a top-level `"decision": "approve"` for UserPromptSubmit

- **Chuzom code:** `src/chuzom/hooks/response_formatter.py:143-152`
  ```python
  def build_echo_output(result: DirectResult, task_type: str, complexity: str) -> dict:
      context = format_echo_context(result, task_type, complexity)
      return {
          "decision": "approve",
          "hookSpecificOutput": {
              "hookEventName": "UserPromptSubmit",
              "additionalContext": context,
          }
      }
  ```
- **Current docs contract:** the UserPromptSubmit decision-control table
  (`hooks.md:1188-1197`) documents exactly one value for `decision`: `"block"`
  ("Omit to allow the prompt to proceed"). No `"approve"` value is documented for
  this event. The only place `"approve"` appears in the fetched docs is the
  PreToolUse deprecation note (§1.1 above), which is unrelated — that's the
  legacy value for a *different* event that maps to `"allow"`.
- **Verdict: UNVERIFIABLE without a live install.** Best-supported reading: an
  unrecognized `decision` value is most likely treated the same as "omitted" (the
  prompt proceeds), making this harmless dead code copied from PreToolUse-style
  logic. But this is exactly the kind of undocumented-value drift a live install
  should confirm doesn't do something unexpected (e.g. get logged as a schema
  warning visible to the user, or silently swallowed in some other way).
- **P2.**

### 1.4 MATCHES — `session-start.py` SessionStart output

- **Chuzom code:** `src/chuzom/hooks/session-start.py:1159-1164`
  ```python
  print(json.dumps({
      "hookSpecificOutput": {
          "hookEventName": "SessionStart",
          "additionalContext": banner + hints,
      }
  }))
  ```
- **Current docs contract** (`hooks.md:979-997`): `hookSpecificOutput.additionalContext`
  nested under `hookEventName: "SessionStart"` — exact match, including field
  nesting.
- **Verdict: MATCHES.** No `sys.exit()` call after printing (falls off the end of
  `main()` → exit 0), which is correct — SessionStart's exit-2 path is
  non-blocking anyway ("Shows stderr to user only").
- Note: `session-start.py` also `print(..., file=sys.stderr)`s a banner/welcome
  box before the JSON (lines 1150-1152). This is fine per the exit-0 contract but
  worth a live-install check that stderr text on a *successful* (exit-0)
  SessionStart doesn't get surfaced twice alongside `additionalContext` in a
  confusing way in the transcript UI.

### 1.5 MATCHES — `stop-enforce.py` Stop hook

- **Chuzom code:** `src/chuzom/hooks/stop-enforce.py` never emits JSON and always
  `sys.exit(0)` (lines 156, 161, 165, 169, 175, 194) — it is purely an
  observational/logging hook (increments a violation-strike counter), matching its
  own docstring: "Never blocks (exit 0 always)."
- **Docs contract:** Stop's decision-control fields (`decision:"block"` /
  `hookSpecificOutput.additionalContext`, `hooks.md:2254-2280`) are simply unused,
  which is a valid no-op per docs ("Omit to allow Claude to stop").
- **Verdict: MATCHES** (trivially — the hook makes no decision-control claims the
  docs could contradict). One gap: it reads only `session_id` from stdin
  (`stop-enforce.py:163`) and never reads/uses `stop_hook_active` even though it
  never blocks, so the omission carries no loop risk today — but if a future
  change adds a `decision:"block"` path here, `stop_hook_active` MUST be checked
  first per docs (`hooks.md:2194`: "Check this value... to avoid blocking on a
  condition that will never resolve. Claude Code overrides the hook and ends the
  turn after 8 consecutive blocks."). Flagging as a **latent trap for future
  edits**, not a current drift.

---

## 2. Findings — Tool Names

### 2.1 MATCHES — `enforce-route.py` `_BASE_BLOCK_TOOLS`

- **Chuzom code:** `src/chuzom/hooks/enforce-route.py:71-73`
  ```python
  _BASE_BLOCK_TOOLS = frozenset({
      "Bash", "Edit", "MultiEdit", "Write", "NotebookEdit",
  })
  ```
- **Current docs:** `Bash`, `Write`, `Edit`, `Read`, `Glob`, `Grep` all have
  dedicated PreToolUse `tool_input` schema sections (`hooks.md:1410-1460`+);
  `NotebookEdit` and `Agent` are documented tool names elsewhere
  (`tools-reference.md`). All five blocklisted names are real, current tool names.
- **DRIFT sub-finding — `MultiEdit` is explicitly called out as legacy in current
  docs**, not merely absent from the newer reference pages:
  `permissions.md:263` (verbatim): *"If you write a path rule for `Write`,
  `NotebookEdit`, `Glob`, or **the legacy `MultiEdit` tool**..."* The `Edit` tool's
  own docs (`tools-reference.md:167-177`) describe `replace_all: true` as Edit's
  mechanism for replacing multiple occurrences — i.e. Edit has absorbed
  MultiEdit's role.
- **Verdict: MATCHES with a staleness note, not a bypass risk.** Blocking a legacy
  tool name is harmless dead weight (not a security gap), and Edit — MultiEdit's
  functional successor — is already blocked, so there is no coverage gap. No
  action required beyond documenting that `MultiEdit` may eventually stop being
  emitted at all by current model versions, at which point this entry becomes
  purely inert.
- **P2** — confirm on a live install whether `MultiEdit` tool calls still occur at
  all with current models; if never, this frozenset can drop it.

### 2.2 MATCHES — Read-only tools exempted from blocking

- **Chuzom code:** `enforce-route.py:1257`: `Read`, `Glob`, `Grep`, `LS` are
  allowed through unconditionally for context-gathering.
- **UNVERIFIABLE sub-finding:** `LS` does not appear as a documented tool name
  anywhere in the three fetched reference pages (`tools-reference.md` has no `LS`
  section; `hooks.md`'s per-tool `tool_input` schema list does not include it).
  This could mean (a) `LS` is an older/legacy tool name Claude Code no longer
  emits (superseded by `Bash(ls ...)` or `Glob`), in which case this line is
  inert, or (b) it's still current but just undocumented on these particular
  pages. Cannot resolve from docs alone.
- **Verdict: harmless either way** — an unreachable exemption for a tool name
  Claude Code never calls does not create a security or enforcement gap (nothing
  can call it, so nothing needs the exemption); if `LS` is in fact still current
  and simply undocumented, the exemption is correct. **P2** — confirm via
  `claude --help` / a live session whether an `LS` tool still exists.

### 2.3 MATCHES — `agent-route.py` registered against the `Agent` matcher

- **Chuzom code:** `install_hooks.py:313`: `("agent-route.py", ..., "PreToolUse", "Agent")`.
- **Docs:** `tools-reference.md:95` — "The Agent tool spawns a subagent..." — `Agent`
  is confirmed as the current canonical subagent-spawning tool name.
- **Verdict: MATCHES.**

---

## 3. Findings — Settings.json Hook Registration

### 3.1 MATCHES — `install_hooks.py._register_hook()` JSON shape

- **Chuzom code:** `src/chuzom/install_hooks.py:498-546`. Writes exactly:
  ```python
  event_hooks.append({
      "matcher": matcher,
      "hooks": [{"type": "command", "command": command}],
  })
  ```
  nested at `settings["hooks"][event]`, and `_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"` (`install_hooks.py:48`).
- **Docs contract:** `hooks.md` verbatim example (PostToolUse):
  ```json
  { "hooks": { "PostToolUse": [ { "matcher": "Edit|Write", "hooks": [ { "type": "command", "command": "/path/to/lint-check.sh" } ] } ] } }
  ```
  — identical shape (event key → array of `{matcher, hooks:[...]}` → `{type, command}`).
  Path matches the documented **User settings** location (`settings.md:83`:
  `~/.claude/settings.json`, "apply to all... projects").
- **Verdict: MATCHES exactly**, including field names and nesting depth.
- **Gap (not drift):** Chuzom never sets an explicit `"timeout"` on any registered
  hook entry. Default is 600s for `type:"command"` (per docs), which is generous,
  but `auto-route.py`'s classification chain does a live Ollama call (default
  `OLLAMA_TIMEOUT=4`s) plus a possible cheap-API fallback plus an inline OAuth
  usage refresh (`_fetch_usage_inline`, 4s timeout) — cumulatively these could
  stack close to a few seconds per prompt but are nowhere near 600s, so this is
  not currently a problem; flagging only because a future addition to the chain
  (e.g. a slower external call) would silently inherit the 600s ceiling with no
  Chuzom-side guard. **P2.**

### 3.2 MATCHES — settings-file precedence assumptions

- Chuzom writes only to the **User** scope (`~/.claude/settings.json`), never to
  `.claude/settings.json` (Project) or `.claude/settings.local.json` (Local) or
  any managed-settings path. Docs confirm User scope is read "in every session
  regardless of which project you open" (`settings.md:135`), which matches the
  global, cross-project nature of Chuzom's routing hooks.
- **Verdict: MATCHES**, appropriate scope choice.

---

## 4. Findings — MCP Registration

### 4.1 MATCHES — `claude mcp add --scope user` primary path + `~/.claude.json` fallback

- **Chuzom code:** `install_hooks.py:577-618` (`_install_claude_code_cli`). Tries
  `claude mcp add --scope user chuzom <cmd> [args...]` first, falls back to a
  direct JSON merge into `~/.claude.json`'s `mcpServers` key.
- **Docs contract:** `mcp.md:420-426` confirms `--scope user` writes into
  `~/.claude.json` and is cross-project/private-to-user, matching intent exactly.
  `mcp.md:80` confirms an entry with `command`+`args` and no `type` key is
  correctly inferred as a `stdio` server (Chuzom's `mcp_entry` dict never sets
  `"type"` explicitly — `install_hooks.py:813,817,1102` — which is fine per this
  rule).
- **Verdict: MATCHES.**

### 4.2 DRIFT — Chuzom also writes an `mcpServers.chuzom` entry directly into `~/.claude/settings.json`, which is not a documented MCP-server-definition location

- **Chuzom code:** `install_hooks.py:819-827`
  ```python
  # ~/.claude/settings.json — Claude Desktop / interactive Claude Code
  settings2 = _load_settings()
  mcp_servers = settings2.setdefault("mcpServers", {})
  if "chuzom" not in mcp_servers:
      mcp_servers["chuzom"] = mcp_entry
      _save_settings(settings2)
      actions.append("Registered chuzom MCP server in ~/.claude/settings.json")
  ```
  The comment explicitly claims this also serves **"interactive Claude Code"**
  (not just Desktop).
- **Current docs contract:** the MCP scope table (`mcp.md:353-361`, verbatim) lists
  exactly three storage locations for `mcpServers` definitions:
  | Scope | File |
  |---|---|
  | Local | `~/.claude.json` |
  | Project | `.mcp.json` |
  | User | `~/.claude.json` |

  `~/.claude/settings.json` is **not** one of them. The only documented role
  `~/.claude/settings.json` plays in the MCP system is holding
  `enabledMcpjsonServers`/`disabledMcpjsonServers` **approval** lists for
  `.mcp.json`-defined servers (`mcp.md:173-177`), not server *definitions*
  themselves.
- **Verdict: DRIFT — likely dead/no-op write for the Claude Code CLI.** The
  redundant, functioning registration is the one at `install_hooks.py:829+`
  (`~/.claude.json`, confirmed correct in §4.1). This one appears to write into a
  key Claude Code's CLI never reads for server discovery. It is plausible this
  path exists for the separate Claude Desktop app's own config format, but the
  code comment conflates that with "interactive Claude Code," and Claude
  Desktop's actual config file is a *different* path already handled elsewhere in
  this same module (`claude_desktop_config_path()`, `install_hooks.py:549-559`,
  which correctly points at `~/Library/Application Support/Claude/claude_desktop_config.json`
  on macOS) — so this settings.json write looks like it duplicates/conflates two
  different products' config surfaces rather than correctly targeting either.
- **Consequence:** low — the real registration path (`~/.claude.json`) still
  succeeds independently, so `chuzom install` likely still results in a working
  MCP connection for Claude Code CLI users. But the `settings.json` write is
  either inert cruft or (worse, unverified) could be silently accepted by
  `_save_settings()`'s schema-less JSON write and then flagged by Claude Code's
  `$schema` validation / startup warnings as an unrecognized/unexpected key —
  needs a live-install check.
- **P1** — verify on a live install: (a) does this write have any observable
  effect at all, (b) does Claude Code warn about an unexpected `mcpServers` key in
  `settings.json`, (c) is this actually intended for the Desktop app's separate
  config, in which case the comment and target path are simply wrong.

---

## 5. Claude Code Features Chuzom Should Adopt But Doesn't

1. **`hookSpecificOutput.permissionDecision` (`allow`/`deny`/`ask`/`defer`) for
   PreToolUse**, replacing the deprecated top-level `decision` (§1.1). `"ask"` in
   particular would let Chuzom show a labeled permission prompt (`[User]` /
   `[Local]`) instead of a hard block for borderline cases, and `"defer"` is the
   only way to integrate cleanly with Agent-SDK/`-p --resume` callers.
2. **`updatedInput`** — Chuzom currently only allows-or-denies a Bash/Edit/Write
   call; it could instead rewrite `tool_input` (e.g., force `run_in_background:
   true`, or append a routing marker) and auto-approve, which is impossible with
   the current top-level `decision` mechanism.
3. **`permission_mode` in hook input** — never read by any Chuzom hook (`grep`
   returned zero matches across `auto-route.py`/`enforce-route.py`). Docs flag
   `permission_mode` (`default`/`plan`/`acceptEdits`/`auto`/`dontAsk`/
   `bypassPermissions`) as relevant to how a hook's `"ask"` interacts with **auto
   mode** specifically (`hooks.md:1559`: *"A hook's `'ask'` also forces a
   permission prompt in auto mode... Before v2.1.211, the classifier could
   approve a Bash command running outside the sandbox without showing the prompt
   the hook requested."*). Given this user's own tooling promotes "auto mode as
   default" (see `/doctor` skill), Chuzom's enforcement hooks should branch on
   `permission_mode` rather than assume one universal permission model.
4. **`SessionEnd` event** — not used at all. `session-end.py` is (correctly, per
   its own docstring) a **Stop**-event hook that fires every turn, not a
   true-once-per-session summary. A dedicated `SessionEnd` hook could produce a
   genuine end-of-session digest instead of a per-turn approximation.
5. **`UserPromptExpansion`** — new event (post-dates most of Chuzom's hook
   design) that fires when a user types `/skillname` directly, a path
   `PreToolUse` cannot see (`hooks.md`: *"a `PreToolUse` hook matching the `Skill`
   tool fires only when Claude calls the tool, but typing `/skillname` directly
   bypasses `PreToolUse`"*). Chuzom's routing currently has no visibility into
   direct slash-command invocation of skills.
6. **`background_tasks`/`session_crons` on Stop input** (v2.1.145+) — could let
   `stop-enforce.py` distinguish "truly done" from "paused for background work,"
   which is directly relevant to its strike-counting logic (a session paused on a
   background task is not necessarily an override).

## 6. Chuzom Assumptions That No Longer Hold / Need Re-verification

1. The code comment at `auto-route.py:2609-2610` ("Claude Code prefers
   `contextForAgent` for higher-priority directives") is not supported by any
   current documentation and appears to be either stale or based on an
   unpublished/internal signal — treat as unverified until confirmed live (§1.2).
2. The `install_hooks.py:581` comment ("`~/.claude/settings.json` is used by
   Claude Desktop [for MCP]") conflates Desktop's actual config file (a
   completely separate path already handled by `claude_desktop_config_path()`)
   with Claude Code's settings.json, and the adjacent comment claims settings.json
   MCP registration also covers "interactive Claude Code," which the current docs'
   three-scope MCP table does not support (§4.2).
3. `_BASE_BLOCK_TOOLS` blocking `MultiEdit` assumes it's still a live, frequently
   emitted tool; current docs label it "legacy" (§2.1) — not broken, but worth
   re-checking whether it fires at all under current model versions before relying
   on it as a meaningful blocklist entry going forward.
4. No Chuzom hook reads `permission_mode`, silently assuming permission-mode
   independence; docs describe explicit `permission_mode`-dependent behavior
   differences for hook `"ask"`/`"allow"` outcomes (§5.3) that Chuzom's `hard`/
   `smart` mode framing (see `~/.claude/rules/chuzom.md`) doesn't currently
   account for.

---

## 7. Prioritized List — What a Formal Audit Must Verify on a Live Claude Code Install

**P0 (blocking — silent-failure risk):**
1. Confirm `{"decision":"block","reason":...}` (legacy top-level, `enforce-route.py:1479`)
   still actually blocks the tool call on the currently-installed Claude Code
   version. If it does not, `hard`/`smart` enforcement is currently a complete
   no-op and every downstream claim in `~/.claude/rules/chuzom.md` about
   enforcement guarantees is false on that install.
2. Record the exact `claude --version` used for every finding above; all findings
   here are dated to whatever build the fetched docs (`code.claude.com/docs`,
   this session) describe, which may be ahead of or behind the user's installed
   binary.

**P1 (should verify soon — plausible but unconfirmed drift):**
3. Confirm whether unknown keys inside `hookSpecificOutput` (e.g. `contextForAgent`)
   are silently ignored or produce a warning/error, and whether the two
   `contextForAgent`-emitting paths in `auto-route.py` (§1.2) actually fail to
   inject context for native Claude Code sessions as this analysis predicts.
4. Confirm whether the `mcpServers.chuzom` entry written into
   `~/.claude/settings.json` (§4.2) has any observable effect for Claude Code CLI
   sessions, or is inert/duplicate of the `~/.claude.json` registration.
5. Confirm whether `MultiEdit` and `LS` tool-call events still occur at all with
   current models (§2.1, §2.2) — determines whether those blocklist/allowlist
   entries are load-bearing or vestigial.

**P2 (lower priority — hygiene / future-proofing):**
6. Confirm the `"decision":"approve"` value in `build_echo_output()` (§1.3) has no
   unexpected side effect for UserPromptSubmit.
7. Consider adopting `hookSpecificOutput.permissionDecision`/`"ask"`/`"defer"`/
   `updatedInput` for PreToolUse ahead of any future removal of the deprecated
   top-level `decision` shim (§1.1, §5.1-5.2).
8. Consider branching enforcement behavior on `permission_mode` (§5.3), and
   evaluate `UserPromptExpansion` / `SessionEnd` / `background_tasks` adoption
   (§5.4-5.6).
9. Explicitly set a hook-level `"timeout"` in `install_hooks.py`'s registration
   calls rather than relying on the 600s default (§3.1) as the classification
   chain grows.
