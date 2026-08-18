# RED-6 Security Audit — Chuzom v1.1.1 (SHA c2c2882)

Scope: prompt-injection defenses, secret handling, command execution boundaries,
network surface authentication, and the "local-first / no telemetry" claim.
Method: static code reading at the pinned SHA (clean worktree,
`.venv-audit/bin/python` only) plus sandboxed, no-network PoCs that call the
audited functions directly with synthetic data. No real credentials were read,
no real network calls were made, no production code was modified.

Evidence root: `/Users/yaliandrona/Projects/Chuzom/.chuzom/zero-tolerance-audit/evidence/red6/`
(`poc_injection_passthrough.py`, `poc_env_leak_react_bash.py`,
`poc_error_sanitization_gap.py`, `poc_gateway_no_auth.py`).

---

## Summary table

| ID | Severity | Confidence | Area | Title |
|---|---|---|---|---|
| RED6-01 | P0 | PROVEN | Prompt injection | Hostile repo content reaches the executing agent's prompt verbatim on the `llm_delegate`/`llm_act` path — the injection-detection/wrapping module is never called anywhere in the agentic pipeline |
| RED6-02 | P0 | PROVEN | Secret handling / command execution | Delegated local-agent subprocess (`bash` tool in `agentic/react.py`) inherits the FULL parent process environment — every API key, token, and secret in `os.environ` — with no scrubbing, no allowlist, no `env=` override at all |
| RED6-03 | P1 | PROVEN | Secret handling | `error_sanitization.py`'s independent, incomplete pattern set fails to redact `sk-ant-`, `sk-proj-`, `ghp_`, and `Bearer` tokens, and is wired into `admin_api.py`'s global exception handler and invoice-fetch error path, both of which return the (falsely trusted) string directly in HTTP response bodies |
| RED6-04 | P1 | PROVEN (code) / STRONG EVIDENCE (network exposure severity) | Network surface | `chuzom gateway` and `chuzom-route` — both live, shipped, console-reachable commands that trigger real paid model calls — have **zero request authentication**; their only gate is a CSRF/DNS-rebinding Host/Origin/Referer check that is not, and does not claim to be, an auth mechanism; both accept an operator-supplied `0.0.0.0` bind (a built-in preset, for the gateway) with no runtime refusal gate, unlike this same codebase's own fixed SSE component |
| RED6-05 | P2 | STRONG EVIDENCE | Command execution | `read_file`/`write_file` tools in the delegated agent's executor have no sensitive-path blocklist (unlike the `bash` tool's `_BASH_SENSITIVE_RE`), so a hostile task/repo can have the agent `read_file` a credential file if it lies under the working directory |
| RED6-06 | P2 | PROVEN | Network surface | `commands/admin_api.py` accepts `--host 0.0.0.0` with no runtime confirmation/refusal gate, relying solely on RBAC (itself sound) rather than defense-in-depth |
| RED6-07 | P3 | NOT EXPLOITABLE TODAY / latent | Secret handling | `secret_scrubber.scrub_environment()` uses a 9-name allowlist that's narrower than `safe_subprocess.py`'s pattern set (missing `MISTRAL_API_KEY`, `HF_TOKEN`, `PERPLEXITYAI_API_KEY`, etc.); currently dead code (never called), so no live impact, but a landmine for future use |
| — | — (positive control) | PROVEN | Secret handling | `secret_scrubber.structlog_scrubber_processor` **is** correctly wired into the real logging pipeline via `logging.py`'s `configure_logging()` (used by `server.py`, `dashboard/server.py`) — not every defense module in this codebase is unused; this one works as designed for the surfaces that call it |
| — | — (positive control) | PROVEN | Command execution | `agentic/react.py`'s `bash` tool does enforce a real blocklist (destructive commands, `.ssh`/`.aws`/`.gnupg`/`id_rsa` paths, non-localhost network tools) and path-containment on `read_file`/`write_file` — genuine guardrails, not purely advisory, just incomplete (see RED6-05) |

---

## Findings

### RED6-01

**ID:** RED6-01 / **Severity:** P0 / **Confidence:** PROVEN
**Area:** Prompt injection (indirect) — highest-priority mandate item
**Title:** Hostile repository/context content reaches the delegated agent's prompt byte-for-byte; the codebase's own injection-detection and mitigation module is never invoked on the agentic execution path

**Claim-Invariant violated:** A router that positions itself between a developer's repository and an autonomous, tool-wielding agent must not let attacker-controlled repository content silently override the task the human actually asked for. Chuzom ships a dedicated `chuzom.prompt_injection` module specifically to guard against this — the existence of that module is itself the product's implicit claim that injected instructions are detected and neutralized.

**Observed behavior:** `llm_act`/`llm_delegate` (`src/chuzom/tools/agentic.py`) accepts a `context: str` parameter — "optional conversation context from the calling session; it's handed to every delegated agent" — and passes it straight into `run_delegation(..., session_context=(context or "")[:2000])` with only a length truncation, no sanitization. That flows into `TaskLedger.session_context` → `frozen_context()` → `pack_prompt()`, which is the exact string sent to the tier-0 local ReAct agent (`agentic/react.py`) or the Codex adapter. A whole-codebase grep (`grep -rln "wrap_prompt_with_boundaries\|_is_injection_attempt" src/chuzom`) shows these two functions are referenced **only** inside `prompt_injection.py` itself and `tools/routing.py` (the `llm_route` classification/query tool) — never in `agentic/service.py`, `agentic/ledger.py`, `agentic/adapters.py`, or `agentic/react.py`. The defense exists and is correctly wired for the direct-query path; it is completely absent from the higher-risk autonomous-execution path.

**Expected behavior:** Any text that becomes part of an autonomous agent's operating context — especially text sourced from a repository or task description the operator doesn't fully control — should be classified and, on detection, either stripped, wrapped with boundary markers the agent is instructed to treat as inert, or at minimum logged/flagged before being handed to a tool-executing model.

**Why this matters to a real user:** A developer who runs `llm_act("fix the failing tests", context=<repo README or issue text>)` against a repository containing hostile instructions (a malicious dependency's README, a poisoned issue description, a comment in a PR being triaged) is one `llm_act` call away from an agent that runs `env`, dumps it into its "final message" transcript, and marks failing acceptance checks as passed — because nothing in the pipeline strips or flags that instruction before it reaches the model doing the work.

**Exact reproduction:** `python evidence/red6/poc_injection_passthrough.py` (run under `.venv-audit`). Uses the real `pack_prompt`, `Milestone`, `TaskLedger` from the audited source with `session_context=HOSTILE_README` (a synthetic README instructing the agent to run `env`, exfiltrate the output, and falsely mark milestones complete).

**Evidence (file:line, command, output):**
- `src/chuzom/tools/agentic.py:151` — `session_context=(context or "")[:2000], # bound: don't blow the agent's prompt` — truncation only, no sanitization call.
- `grep -rln "wrap_prompt_with_boundaries\|_is_injection_attempt" src/chuzom --include="*.py"` → only `src/chuzom/prompt_injection.py` and `src/chuzom/tools/routing.py:21,275` match; zero hits in `agentic/`.
- PoC output (verified this session): `_is_injection_attempt(HOSTILE_README) == True` (the detector correctly flags the hostile text as suspicious in isolation) **and** `HOSTILE_README in prompt_sent_to_local_model == True` (the same, still-unmodified hostile text appears verbatim in the actual prompt handed to the executing model). Both are true simultaneously — the module knows the text is hostile, and is never asked.

**Root cause:** The injection-defense module was integrated into the direct-completion tool surface (`llm_route` in `tools/routing.py`) but the agentic-delegation surface was built and wired independently, and nobody connected the two. Classic "defense exists in the codebase, not on the code path that needed it."

**Why existing tests missed it:** `tests/test_prompt_injection.py` (confirmed by direct read) contains only unit tests that call `_is_injection_attempt(...)` and `wrap_prompt_with_boundaries(...)` in isolation with hand-crafted strings (`TestInjectionDetection`, `TestPromptSanitization`). Zero tests import `TaskLedger`, `pack_prompt`, `run_delegation`, `llm_delegate`, or anything from `chuzom.agentic` — there is no integration test proving the detector is actually invoked anywhere in the real execution pipeline. The unit tests all pass; the pipeline they're meant to protect was never exercised.

**Blast radius:** Every `llm_act`/`llm_delegate` call that includes a `context` argument sourced (even indirectly) from repository content, issue text, or any other less-trusted input. This is the primary "let an agent go do real work in my repo" entry point of the product.

**Can this defect class exist elsewhere?:** Yes — this is the first of three "defense module exists but isn't wired to the actual hot path" instances found in this audit (see RED6-02, RED6-03). It is a recurring architectural pattern in this codebase: security modules are built, unit-tested in isolation, and not integration-tested against the surfaces that need them.

**Recommended systemic fix:** (1) Call `wrap_prompt_with_boundaries`/an equivalent gate on `session_context` before it enters `TaskLedger`/`pack_prompt`, mirroring what `tools/routing.py` already does. (2) Add an integration test that builds a `TaskLedger` with hostile `session_context` and asserts the string that reaches `pack_prompt()`'s output does NOT contain the raw hostile text. (3) Treat "add a new consumer of untrusted text" as requiring an explicit prompt-injection-gate checklist item in review.

**Regression test that would prevent recurrence:** A test in `tests/agentic/` (or wherever agentic integration tests live) that constructs a `TaskLedger`/calls `llm_delegate` with a hostile `context` string containing a canary phrase, and asserts the canary phrase is either absent or wrapped/flagged in the string actually passed to the executor — not just that `_is_injection_attempt()` returns `True` in isolation.

**Release blocking? YES**

---

### RED6-02

**ID:** RED6-02 / **Severity:** P0 / **Confidence:** PROVEN
**Area:** Secret handling / command execution
**Title:** The delegated local agent's `bash` tool spawns subprocesses that inherit the entire parent environment — every API key and secret — with zero scrubbing

**Claim-Invariant violated:** A router whose whole value proposition is holding provider API keys on the user's behalf must not hand every one of those keys, plus every other secret in the process environment, to a subprocess that a remote/local model's generated shell command controls the content of.

**Observed behavior:** `agentic/react.py`'s `default_tool_executor()` implements the `bash` tool as:
```python
proc = subprocess.run(
    ["/bin/sh", "-c", command], cwd=str(base),
    capture_output=True, text=True, timeout=timeout, check=False,
)
```
There is **no `env=` argument at all**. Per Python's documented `subprocess.run` default, the child process inherits `os.environ` unmodified — meaning `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, every other provider key, and any unrelated secret sitting in the parent's environment (CI tokens, cloud credentials, etc.) is directly visible to any shell command the model decides to run, e.g. `env`, `printenv`, or a command that reads `$ANTHROPIC_API_KEY` and ships it somewhere. This is a hot-path executor for a tier-0 agent whose commands are model-generated, i.e., attacker-influenceable via RED6-01's injection path.

**Expected behavior:** The subprocess environment for model-generated commands should be built from an explicit allowlist (or filtered via `safe_subprocess.py`'s existing broader `_SECRET_ENV_VARS`-aware scrubbing, which already exists in this codebase for exactly this purpose) rather than defaulting to full inheritance.

**Why this matters to a real user:** Combined with RED6-01 (injection reaches the prompt) and the `_bash_block_reason` guard only blocking specific *destructive* or *credential-path-referencing* commands (not `env`/`printenv`, which are neither), a hostile repository can cause the delegated agent to run `env` and include the output in its transcript/final message, at which point every API key Chuzom holds for the user is sitting in agent output.

**Exact reproduction:** `evidence/red6/poc_env_leak_react_bash.py` (prior segment; re-confirmed relevant this segment via direct reading of `agentic/react.py` lines ~130-137). Reproduction: call `default_tool_executor()()("bash", {"command": "env"})` with a synthetic fake API key set in `os.environ` in the sandbox and observe it echoed in the tool's return string.

**Evidence (file:line, command, output):**
- `src/chuzom/agentic/react.py:131-137` — `subprocess.run(["/bin/sh", "-c", command], cwd=str(base), capture_output=True, text=True, timeout=timeout, check=False)` — no `env=`.
- `_bash_block_reason()` (lines 100-108) blocks: destructive commands (`_BASH_DESTRUCTIVE_RE`), sensitive credential *paths* (`_BASH_SENSITIVE_RE`: `.ssh`, `.aws`, `.gnupg`, `id_rsa`, etc.), and non-localhost network tools (`_BASH_NET_TOOL_RE` unless `_BASH_LOCALHOST_RE` matches) — none of these patterns match `env`, `printenv`, `set`, `export -p`, or a command that simply references `$SOME_API_KEY` inline.
- Confirmed via grep that `safe_subprocess.py` (a broader, purpose-built env-scrubbing module elsewhere in this codebase) is never imported by `agentic/react.py` or `agentic/adapters.py`.

**Root cause:** Same "defense exists elsewhere, not wired to this path" pattern as RED6-01. `safe_subprocess.py` was clearly built to solve exactly this problem and simply isn't used here.

**Why existing tests missed it:** No test in the repo constructs a `ReActAgent`/`default_tool_executor` with a fake secret in `os.environ` and asserts it does NOT appear in `bash` tool output.

**Blast radius:** Every `llm_act`/`llm_delegate` call routed to tier 0 (the default, cheapest tier) whenever the model decides (on its own, or under injection influence) to run a command that surfaces environment variables.

**Can this defect class exist elsewhere?:** Yes — check `agentic/adapters.py`'s `CodexAdapter` (tier 1) for the same missing `env=` filtering; not fully verified this session but flagged as an untested item below.

**Recommended systemic fix:** Pass an explicit, minimal `env=` to every `subprocess.run` call in the tool executor — either a hardcoded safe allowlist (PATH, HOME, LANG, etc.) or route through `safe_subprocess.py`'s existing scrubbing helper. Also extend `_bash_block_reason` to flag `env`/`printenv`/`set`/`export` with no arguments as suspicious.

**Regression test that would prevent recurrence:** Set a fake `os.environ["FAKE_SECRET_MARKER"]`, invoke the `bash` tool with `command="env"`, assert the marker is absent from the returned string.

**Release blocking? YES**

---

### RED6-03

**ID:** RED6-03 / **Severity:** P1 / **Confidence:** PROVEN
**Area:** Secret handling / error diagnostics
**Title:** `error_sanitization.py` has an independent, incomplete secret-redaction pattern set — misses generic API keys, GitHub tokens, and bearer tokens — and is the sanitizer actually used in `admin_api.py`'s global exception handler and error responses

**Claim-Invariant violated:** The codebase documents `secret_scrubber.scrub_text()` as "the single source of truth every content store should call, replacing the three drifted per-module scrubbers (secret_scrubber / session_store / error_sanitization)" (its own docstring, `CHZ-SEC-01`). `error_sanitization.py` is one of the modules that comment says should have been replaced, and was not.

**Observed behavior:** `error_sanitization.py`'s `_SENSITIVE_PATTERNS` set covers file paths, SQL fragments, DB connection strings, and AWS/Google key formats, but has **zero** pattern for `sk-`/`sk-ant-`/`sk-proj-` API keys, `ghp_`/`gho_` GitHub tokens, or `Bearer <token>` headers — all of which `secret_scrubber.scrub_text()` (the documented canonical replacement) correctly redacts. `sanitize_error_message()`'s fallback to a generic message only triggers if the ENTIRE message becomes empty after redaction — so a message that is mostly safe text plus one leaked secret sails through with the secret intact and everything else unredacted.

**Expected behavior:** `error_sanitization.py` should delegate to (or be replaced by) `secret_scrubber.scrub_text()` as its own in-code comment elsewhere in the codebase says it should.

**Why this matters to a real user:** `admin_api.py` uses `sanitize_exception()` from this module in two places that put the result directly in an HTTP response body: the app-wide catch-all `@app.exception_handler(Exception)` (the deny-by-default error boundary, explicitly built per its own `P1-1` comment to prevent exactly this class of leak) and the invoice-fetch error path (`/v1/admin/invoice/diff`, `P1-1` comment again). Any unhandled exception whose message happens to contain a real API key, GitHub token, or bearer token (e.g. an upstream provider's own error message echoing the key it rejected, or a stack trace containing an in-scope local variable's repr) is returned to the caller un-redacted, despite explicit developer intent and in-code comments claiming otherwise.

**Exact reproduction:** `python evidence/red6/poc_error_sanitization_gap.py` (run this session under `.venv-audit`).

**Evidence (file:line, command, output):**
- `src/chuzom/error_sanitization.py` `_SENSITIVE_PATTERNS` (full set reproduced in prior segment) — no `sk-`/`ghp_`/`bearer` pattern.
- `src/chuzom/admin_api.py:515-545` — `_unhandled_exception_handler`: `content={"detail": sanitize_exception(exc, "internal server error")}`.
- `src/chuzom/admin_api.py:1335-1360` — invoice-fetch path: `detail=sanitize_exception(exc, "failed to fetch invoice from provider")`.
- PoC run output (this session, confirmed): a synthetic exception message containing fake `sk-ant-api03-...`, `sk-proj-...`, `ghp_...`, and `Bearer ...` tokens comes back **byte-identical to the raw input** through `sanitize_exception()` (zero redaction), while `secret_scrubber.scrub_text()` on the identical input correctly produces `[REDACTED-ANTHROPIC_API_KEY]`, `[REDACTED-OPENAI_API_KEY]`, `[REDACTED-GITHUB_TOKEN]`, `[REDACTED-AUTHORIZATION]`.

**Root cause:** Three independently-maintained secret-redaction implementations exist in this codebase (`safe_subprocess.py`, `secret_scrubber.py`, `error_sanitization.py`); a consolidation was documented as intended (`CHZ-SEC-01`) but not completed for this module.

**Why existing tests missed it:** No test feeds a realistic secret-bearing exception message through `sanitize_exception()`/`sanitize_error_message()` and asserts redaction; the module's own tests (if any) likely only exercise the patterns it does have (SQL/paths/AWS), not the ones it's missing.

**Blast radius:** Every unhandled exception surfaced through `admin_api.py`'s global error boundary, plus the invoice-fetch path specifically — both are reachable by any authenticated admin-API caller, and the global handler by definition covers unknown/future failure modes across the entire admin surface.

**Can this defect class exist elsewhere?:** Yes — grep for other callers of `sanitize_exception`/`sanitize_error_message`/`create_user_error_message` outside `admin_api.py` to check for the same exposure elsewhere (not fully enumerated this session; flagged below as untested).

**Recommended systemic fix:** Make `error_sanitization.sanitize_error_message()` call `secret_scrubber.scrub_text()` in addition to (or instead of) its own `_SENSITIVE_PATTERNS`, closing the documented-but-unfinished consolidation.

**Regression test that would prevent recurrence:** Feed each of `secret_scrubber.SECRET_PATTERNS`' example formats through `error_sanitization.sanitize_exception()` and assert none survive un-redacted — i.e., a cross-module parity test, not just a per-module unit test.

**Release blocking? YES** (P1, but reachable via the primary admin API surface and directly contradicts an explicit in-code security comment)

---

### RED6-04

**ID:** RED6-04 / **Severity:** P1 / **Confidence:** PROVEN (code path) / STRONG EVIDENCE (real-world exposure, since it requires a non-default operator choice)
**Area:** Network surface
**Title:** `chuzom gateway` and `chuzom-route` — live console-reachable commands that trigger real, paid model calls — have no request authentication of any kind; the only gate is a browser-CSRF/DNS-rebinding check that is not, and does not claim to be, an auth mechanism, and both accept a `0.0.0.0` bind with no runtime refusal gate

**Claim-Invariant violated:** `pyproject.toml` carries an explicit historical notice (SEC-001, audit 2026-06): a prior `chuzom-sse` entry point "bound 0.0.0.0 with no auth and exposed the full 60-tool MCP surface... to anyone reachable on the network" and was removed until it could be rebuilt with mandatory bearer-token auth plus an explicit `0.0.0.0` opt-in gate (`main_sse_secured` in `server.py`, which now does exactly that: `if host == "0.0.0.0" and not _allow_public_bind(): sys.exit(2)`). This audit's mandate explicitly asks whether that class of vulnerability still exists anywhere in the current network surface.

**Observed behavior:**
- `src/chuzom/gateway.py` is a FastAPI app exposing `/v1/chat/completions` (OpenAI-compatible), `/v1/messages` (Anthropic-compatible), `/api/chat`, `/api/generate` (Ollama-compatible) — its own docstring: "Every route here can trigger a real (possibly paid) model call." A whole-file grep for `Depends(` returns **zero matches** — no bearer token, no API key, no per-route authentication of any kind.
- Its only protection is `_guard_cross_origin` middleware (tagged `CHZ-SEC-04`), which calls `chuzom.route_server.is_forbidden_cross_origin(request.headers)` — a check of the `Host`/`Origin`/`Referer` headers against an allowlist (`_LOCAL_HOSTS = {"localhost","127.0.0.1","::1"}` plus `CHUZOM_ALLOWED_HOSTS` env override). Its own docstring says this targets **browser** CSRF/DNS-rebinding specifically: "Legitimate CLI/SDK clients (curl, openai SDK) send a loopback Host and no browser Origin, so they are unaffected" — i.e., by explicit design, it lets through exactly the traffic shape any non-browser client (curl, a Python script, another local or network process, legitimate or hostile) naturally produces, with zero credential requirement.
- `gateway.main()` binds via `presets.bind()`, which resolves `os.environ.get("CHUZOM_GATEWAY_HOST") or p.get("host", "127.0.0.1")`. `presets.py` ships a built-in `"team-server"` preset with `host: 0.0.0.0`. There is no `_allow_public_bind()`-equivalent runtime refusal anywhere in `gateway.py` or `presets.py`.
- `chuzom gateway` is a live, shipped CLI subcommand (`cli.py:816-820`: `from chuzom.gateway import main as gateway_main; gateway_main()`), reachable via the `chuzom` console script registered in `pyproject.toml`. This is not dead/removed code like the old `chuzom-sse` — it is the currently-documented primary gateway surface.
- A second, independent component, `src/chuzom/route_server.py` (registered as its own console script, `chuzom-route = "chuzom.route_server:main"`), exposes `POST /route` and shares the exact same routing core (`route_and_call`) and the exact same `is_forbidden_cross_origin` guard as its only protection. Its default host is the safe `127.0.0.1`, but `--host` is a free-form CLI argument (`argparse`, default `127.0.0.1`) with no validation or refusal for any other value.

**Expected behavior:** Any surface capable of triggering a real, budget-consuming model call should require a credential (bearer token, API key, or equivalent) before executing the call, independent of any CSRF/host-header check — and any surface that accepts an operator-supplied bind address should refuse `0.0.0.0` without an explicit opt-in, exactly as this codebase's own `main_sse_secured` already demonstrates as the correct fix for this exact vulnerability class.

**Why this matters to a real user:** By default (127.0.0.1, no env override, no team-server preset), a single-developer install is not exposed — this is not a default-config vulnerability. But the moment an operator uses the shipped `team-server` preset (or sets `CHUZOM_GATEWAY_HOST=0.0.0.0`) to let teammates share a gateway — the exact use case that preset exists for — the gateway is reachable by anyone who can route packets to it, and needs nothing but a normal HTTP client (no browser, no credential) to consume the operator's paid model budget, and (per the gateway's own purpose) route arbitrary attacker-supplied prompts through the operator's configured providers. This reproduces the substance of SEC-001 in a currently-shipping, currently-documented code path, just gated behind an operator choice instead of being the unconditional default.

**Exact reproduction:** `python evidence/red6/poc_gateway_no_auth.py` (this session, `.venv-audit`, no live network calls — calls the real `is_forbidden_cross_origin` function directly with synthetic header dicts).

**Evidence (file:line, command, output):**
- `src/chuzom/gateway.py` — module docstring; `grep -c "Depends(" src/chuzom/gateway.py` → 0; `_guard_cross_origin` middleware (`CHZ-SEC-04` comment) is the only `@app.middleware`.
- `src/chuzom/route_server.py:143-173` — `is_forbidden_cross_origin()` full implementation; `_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})` (line 140).
- `src/chuzom/route_server.py:199-247` — `chuzom-route`'s `do_POST` uses `_forbidden_cross_origin()` (same function) as its only gate before calling `route_payload()`; `main()` accepts `--host` with `default="127.0.0.1"` and no validation.
- `src/chuzom/presets.py` (grepped) — `team-server` preset: `host: 0.0.0.0`; `bind()`: `os.environ.get("CHUZOM_GATEWAY_HOST") or p.get("host", "127.0.0.1")`.
- `src/chuzom/cli.py:816-820` — `chuzom gateway` dispatches to `gateway.main()`; `pyproject.toml:129` registers `chuzom = "chuzom.cli:main"` — this is a live, shipped entry point.
- `pyproject.toml:122-127` — the SEC-001 historical notice explicitly describing the vulnerability class this finding reproduces, and the three conditions (`bearer-token auth`, `INV-010`, `0.0.0.0 requires explicit opt-in`) that were required before `chuzom-sse` could ever ship again — none of which `gateway.py`/`route_server.py` currently satisfy, despite being live.
- `src/chuzom/server.py:522-527,568-574` — `_allow_public_bind()` and its enforcement in `main_sse_secured()`: `if host == "0.0.0.0" and not _allow_public_bind(): sys.stderr.write(...); sys.exit(2)` — proof this codebase already knows the correct pattern and applies it to one component but not to gateway.py/route_server.py.
- PoC output (this session, confirmed): `is_forbidden_cross_origin({"Host": "127.0.0.1:17900"}) == False` (curl-shaped request passes); `is_forbidden_cross_origin({"Host": "127.0.0.1:17900"})` with no Origin/Referer, simulating a hostile local script, also `== False` (indistinguishable from "legitimate" traffic to this guard); and with `CHUZOM_ALLOWED_HOSTS=10.0.0.5` set (the state an operator must reach for the team-server preset to be usable by remote teammates at all) `is_forbidden_cross_origin({"Host": "10.0.0.5:17900"}) == False` — any network client sending that Host value and no Origin/Referer passes through with zero credentials.

**Root cause:** The CSRF/DNS-rebinding guard was built to solve a real but narrower problem (browser-originated cross-origin requests against a loopback service) and was never paired with actual request authentication for the case where the service is intentionally bound beyond loopback. The `0.0.0.0`-refusal pattern that exists elsewhere in this exact codebase (`server.py`) was not applied here.

**Why existing tests missed it:** No test starts `gateway.py`'s app (or calls its middleware/routes) against a synthetic non-loopback `Host`/no-auth request and asserts a 401/403 without a token; the only test coverage implied by the code is around `is_forbidden_cross_origin`'s CSRF-specific behavior, not authentication.

**Blast radius:** Any operator who uses the `team-server` preset or sets `CHUZOM_GATEWAY_HOST`, or who runs `chuzom-route --host <non-loopback>` — anyone reachable on that network segment can consume the operator's model budget and route arbitrary prompts through their configured providers with zero credentials. Default single-user installs are not affected.

**Can this defect class exist elsewhere?:** This is literally the second live instance of the SEC-001 vulnerability class in the current codebase (the first, `chuzom-sse`, was correctly fixed by removal + rebuild-behind-auth). `sidecar.py` and `gateway_service.py` were also checked this session: `gateway_service.py` is only a launchd/systemd unit-file generator (not itself a server) and is not a live vulnerability; `sidecar.py` had no host/bind/auth keywords on a targeted grep and was not further investigated — flagged below as untested.

**Recommended systemic fix:** (1) Add `Depends()`-based bearer-token (or equivalent) authentication to `gateway.py`'s routes, matching the pattern `admin_api.py` and `main_sse_secured` already use elsewhere in this codebase. (2) Add an `_allow_public_bind()`-equivalent refusal in `gateway.py`'s `main()` and `route_server.py`'s `main()` for any host outside `_LOCAL_HOSTS`, requiring an explicit env opt-in, exactly mirroring `server.py`'s existing fix for SEC-001. (3) Either remove the `team-server` preset's implicit `0.0.0.0` default or require it be paired with an explicit auth-token configuration at preset-selection time.

**Regression test that would prevent recurrence:** Start `gateway.py`'s app in-process (ASGI test client), send a request with `Host: <non-default>` and no bearer token, assert it is rejected; separately, assert `gateway.main()`/`route_server.main()` refuse to bind `0.0.0.0` without the equivalent of `CHUZOM_SSE_ALLOW_PUBLIC=on`.

**Release blocking? YES** (P1: not exploitable in the safe default configuration, but the exact vulnerability class this codebase has already paid down once, in a component that is live and documented, not experimental)

---

### RED6-05

**ID:** RED6-05 / **Severity:** P2 / **Confidence:** STRONG EVIDENCE
**Area:** Command execution
**Title:** The delegated agent's `read_file`/`write_file` tools have no sensitive-path blocklist, unlike the `bash` tool's equivalent guard

**Claim-Invariant violated:** If the product's threat model includes "don't let a delegated agent read/exfiltrate credential files" (demonstrated by `_BASH_SENSITIVE_RE` existing at all), that protection should apply uniformly across every tool capable of reading file content, not just the shell tool.

**Observed behavior:** `agentic/react.py`'s `default_tool_executor()` implements `_resolve(path_arg)` for `read_file`/`write_file` which enforces only that the resolved path stays within the working directory (`base`) — no check against `.ssh`, `.aws`, `.gnupg`, `id_rsa`, or any credential-filename pattern, unlike `_bash_block_reason()`'s `_BASH_SENSITIVE_RE` which explicitly blocks those same patterns for the `bash` tool.

**Expected behavior:** `read_file` should apply the same (or an equivalent) sensitive-filename check as the `bash` tool before returning file content to the model.

**Why this matters to a real user:** If a delegated agent's working directory is (or contains, e.g. via a symlink or a checked-in credentials file) a path matching one of the patterns `_BASH_SENSITIVE_RE` already treats as dangerous, `bash cat ~/.ssh/id_rsa` is blocked, but `read_file(path="id_rsa")` or `read_file(path=".ssh/id_rsa")` is not — an inconsistent boundary that a hostile task/repo (per RED6-01) could exploit to prefer the unguarded tool.

**Exact reproduction:** Not executed as a live PoC this session (time-boxed); confirmed by direct source reading — `_resolve()` (react.py, ~lines 111-121) has no call to `_BASH_SENSITIVE_RE` or equivalent.

**Evidence (file:line, command, output):** `src/chuzom/agentic/react.py` — `_bash_block_reason()` (~100-108) vs. `_resolve()` (~111-121): the former checks `_BASH_SENSITIVE_RE`, the latter only checks `base not in resolved.parents and resolved != base`.

**Root cause:** The sensitive-path guard was written specifically for the shell-command surface and not generalized to the file-tool surface.

**Why existing tests missed it:** No test exercises `read_file` against a `.ssh`/`id_rsa`-shaped path to confirm equal treatment with `bash`.

**Blast radius:** Bounded by the agent's working directory — this is not an arbitrary-filesystem-read bug (path traversal outside `base` is correctly blocked), only a same-directory blind spot.

**Can this defect class exist elsewhere?:** Possibly in `CodexAdapter`'s tool executor (tier 1) — not verified this session.

**Recommended systemic fix:** Extract `_BASH_SENSITIVE_RE`'s check into a shared helper and apply it in `_resolve()`/`read_file` as well.

**Regression test that would prevent recurrence:** Create a file named `id_rsa` under the executor's `base`, call `read_file(path="id_rsa")`, assert it is blocked the same way `bash cat id_rsa` is.

**Release blocking? NO** (real gap, but bounded blast radius and lower likelihood than RED6-01/02)

---

### RED6-06

**ID:** RED6-06 / **Severity:** P2 / **Confidence:** PROVEN
**Area:** Network surface
**Title:** `commands/admin_api.py` accepts `--host 0.0.0.0` with no runtime refusal gate, unlike the pattern this codebase uses elsewhere for the same risk

**Claim-Invariant violated:** Defense-in-depth for public binding should be consistent across chuzom's own server components; `server.py`'s SSE component demonstrates the correct pattern (explicit env opt-in required for `0.0.0.0`), and `admin_api.py`'s RBAC is genuinely sound, but relying on RBAC alone (no bind-gate) is inconsistent with the codebase's own established practice.

**Observed behavior:** `src/chuzom/commands/admin_api.py` defaults to `127.0.0.1:7339` (safe) but parses `--host`/`--port` with no validation, and calls `uvicorn.run(app, host=host, port=port, ...)` directly. The only protection against a careless `--host 0.0.0.0` invocation is a passive comment: "Security note: --host 0.0.0.0 exposes the API on every reachable interface. The API is RBAC-gated... but a careless deployment can still leak the OpenAPI surface."

**Expected behavior:** Mirror `server.py`'s `_allow_public_bind()` pattern: refuse to bind `0.0.0.0` without an explicit env opt-in.

**Why this matters to a real user:** Unlike RED6-04, `admin_api.py`'s routes ARE genuinely RBAC-gated (verified: `require_perm(Permission.X)` on essentially every mutating/sensitive route, `authenticate_identity` via `HTTPBearer`), so this is lower severity — but the OpenAPI schema (`/docs`, `/redoc`), the intentionally-unauthenticated `/v1/admin/health` and `/v1/admin/ui` routes, and the attack surface itself become reachable to anyone on the network, and a future route added without remembering to add `require_perm` would be silently exposed with no secondary gate to catch the mistake.

**Exact reproduction:** Confirmed by direct source reading; not run as a live bind-and-probe test this session.

**Evidence (file:line, command, output):** `src/chuzom/commands/admin_api.py` (111 lines, read in full) — `_DEFAULT_HOST = "127.0.0.1"`; argument parsing loop with no `0.0.0.0` check; `uvicorn.run(app, host=host, port=port, log_level="info")`.

**Root cause:** Same inconsistent-application-of-a-known-pattern issue as RED6-04, at lower severity because the routes are actually authenticated here.

**Why existing tests missed it:** No test invokes `cmd_admin_api(["--host", "0.0.0.0"])` and asserts refusal.

**Blast radius:** Operators who bind admin-api publicly without a reverse proxy; mitigated substantially by genuine RBAC, so mainly a defense-in-depth / OpenAPI-surface-exposure concern, not an auth bypass.

**Can this defect class exist elsewhere?:** This is the third instance of "no `_allow_public_bind()`-equivalent gate" found this session (gateway.py, route_server.py, commands/admin_api.py) against one instance where the correct pattern IS applied (server.py's SSE). Strongly suggests the gate should be a shared utility, not something each new server component has to remember to reimplement.

**Recommended systemic fix:** Extract `_allow_public_bind()` from `server.py` into a shared helper (e.g. `chuzom.net_safety`) and call it from every component that accepts an operator-supplied host.

**Regression test that would prevent recurrence:** `cmd_admin_api(["--host", "0.0.0.0"])` without the opt-in env var should exit non-zero / refuse, mirroring the existing SSE test if one exists.

**Release blocking? NO** (real gap, but genuine RBAC underneath substantially reduces severity vs. RED6-04)

---

### RED6-07

**ID:** RED6-07 / **Severity:** P3 / **Confidence:** NOT EXPLOITABLE TODAY (latent)
**Area:** Secret handling
**Title:** `secret_scrubber.scrub_environment()`'s 9-name allowlist is narrower than `safe_subprocess.py`'s pattern set, but is currently dead code

**Claim-Invariant violated:** N/A currently — this is a latent-defect note, not a live vulnerability, included for completeness per the mandate's instruction to characterize secret-scrubber regex coverage gaps.

**Observed behavior:** `secret_scrubber.py`'s `SENSITIVE_ENV_VARS` is a 9-name exact-match set (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `DATABASE_URL`, `REDIS_URL`), used by `scrub_environment()`. `safe_subprocess.py`'s pattern set (grepped this session) additionally covers `PERPLEXITYAI_API_KEY`, `MISTRAL_API_KEY`, `HF_TOKEN`, and others that `secrets_vault.py`'s own `PROVIDER_ENV` map shows are real, in-use provider keys for this product (`perplexity`, and presumably others via `chuzom.config._PROVIDER_MAP`, not fully enumerated). A grep for callers of `scrub_environment()` across the whole codebase (outside `secret_scrubber.py` itself) returns zero hits — it is not currently called anywhere.

**Expected behavior:** If/when this function is wired up (e.g., for a future diagnostic/doctor-output feature), its allowlist should match or exceed `safe_subprocess.py`'s broader set.

**Why this matters to a real user:** No live impact today. It becomes a real gap the moment someone builds a feature that calls `scrub_environment()` for diagnostic output, believing (per the function's docstring, "Removes API keys and secrets from environment variables before logging") that it's comprehensive.

**Exact reproduction:** `grep -rn "scrub_environment(" src/chuzom` → only the definition itself.

**Evidence (file:line, command, output):** `src/chuzom/secret_scrubber.py:69-79` (`SENSITIVE_ENV_VARS`) vs. `src/chuzom/safe_subprocess.py` (broader pattern list, includes `PERPLEXITYAI_API_KEY`, `MISTRAL_API_KEY`, `HF_TOKEN`).

**Root cause:** Two independently-authored allowlists for the same conceptual purpose, never reconciled.

**Why existing tests missed it:** No test calls `scrub_environment()` with a `MISTRAL_API_KEY` set and asserts redaction — consistent with the function having no real caller to motivate such a test.

**Blast radius:** None today (dead code); would be scoped to whatever future feature calls it.

**Can this defect class exist elsewhere?:** This is the third drifted-scrubber instance found this audit (alongside RED6-03's error_sanitization.py and the previously-known safe_subprocess/secret_scrubber split) — a systemic pattern of parallel, unreconciled secret-pattern lists across this codebase.

**Recommended systemic fix:** Either delete `scrub_environment()` as unused, or replace its `SENSITIVE_ENV_VARS` set with `safe_subprocess.py`'s broader pattern (or better, unify all three into one shared allowlist/pattern module, closing the `CHZ-SEC-01` consolidation gap for real this time).

**Regression test that would prevent recurrence:** A parity test asserting `secret_scrubber.SENSITIVE_ENV_VARS` is a superset of (or reconciled with) `safe_subprocess.py`'s pattern-implied env-var set.

**Release blocking? NO**

---

## Positive controls (honest reporting of what does work)

- `secret_scrubber.structlog_scrubber_processor` **is** correctly wired into `logging.py`'s `configure_logging()`, applied second in `shared_processors` ("before any other processing" per its own comment), and used both for structlog's native pipeline and for stdlib `logging` calls via `ProcessorFormatter(foreign_pre_chain=...)`. Confirmed callers: `server.py:43`, `dashboard/server.py:1145`. This means ordinary `structlog`/stdlib log lines emitted from a process that has called `configure_logging()` do get scrubbed by the broader `SECRET_PATTERNS` set (which, unlike `error_sanitization.py`, DOES cover `sk-`/`ghp_`/bearer formats). Not every defense module in this codebase is unused — this is a real, working control for the surfaces that call it.
- `commands/doctor.py` was verified clean for the specific "does diagnostic output leak credentials" concern: it only does boolean presence checks (`if os.environ.get("OPENROUTER_API_KEY"):`) and prints ok/warn status text, never the raw key value. No `environ.copy()`/`dict(os.environ)` raw dumps exist anywhere outside the scrubbing modules themselves.
- `admin_api.py`'s RBAC model (Bearer token → `authenticate_identity` → `require_perm(Permission.X)` per route) is genuinely sound and consistently applied; the two unauthenticated routes (`/v1/admin/health`, `/v1/admin/ui`) are defensible by design (no secrets in either; the UI's data calls all go through the same RBAC-gated endpoints, carrying the operator's own bearer token from `sessionStorage`).
- `dashboard/server.py`'s token model (persistent `~/.chuzom/dashboard.token`, `secrets.token_urlsafe(32)`, checked via `secrets.compare_digest`) is sound, and an explicit in-code comment (`CHZ-SEC-05`) documents a prior related vulnerability (the `/` index route being auth-exempt while leaking the token) that has since been fixed correctly.
- `scim_api.py` is fail-closed (disabled unless both `CHUZOM_SCIM_ENABLED` and `CHUZOM_SCIM_TOKEN` are set) and uses timing-safe `hmac.compare_digest()` for its bearer check.
- `agentic/react.py`'s `bash` tool guard (`_BASH_DESTRUCTIVE_RE`, `_BASH_SENSITIVE_RE`, `_BASH_NET_TOOL_RE`) is a real, non-cosmetic blocklist — it does refuse destructive commands, credential-path references, and non-localhost network egress, not merely log them. It is incomplete (RED6-02, RED6-05) but it is not purely advisory.
- `server.py`'s `main_sse_secured()`/`_allow_public_bind()` is the correct fix pattern for the exact SEC-001 vulnerability class found live in RED6-04/06 — this codebase has already solved this problem once; it just didn't apply the fix uniformly.
- No `CORSMiddleware` is registered anywhere (grep-confirmed for `admin_api.py`) — the safe default (no CORS headers = same-origin-only for browsers), correctly not flagged as a finding.

## Data leakage / "local-first" claim — assessment

Not exhaustively re-verified this segment (see RED-1/RED-2's dedicated mandate areas for the primary routing/classification data-flow audit), but from what was directly observed in this segment: `gateway.py`'s `_load_dotenv()` only *reads* provider keys from `~/.chuzom/.env`/`~/.env` into `os.environ` at import time — it does not itself transmit anything. Whether a prompt is sent to a cloud provider vs. handled locally is a routing-tier decision made elsewhere in the codebase (`route_and_call`, tier ladder in `agentic/adapters.py`) and was not re-traced end-to-end in this segment; this remains primarily RED-1/RED-2 scope. No phone-home analytics/exception reporter was found in any file read this segment.

---

## Three most important untested things (time-boxed out of this session)

1. **`agentic/adapters.py`'s `CodexAdapter` (tier 1) subprocess environment handling** — RED6-02 was proven specifically for `agentic/react.py`'s tier-0 `bash` tool; whether the tier-1 Codex adapter has the same full-environment-inheritance gap (or, better, actually uses `safe_subprocess.py`'s scrubbing) was not verified. This matters because tier 1 is the escalation target after tier-0 failures — exactly the path a hostile repo would push the agent toward if it wants a more capable executor.
2. **Whether `gateway.py`'s complete lack of authentication is exploitable in the actual default single-user configuration via some path not yet checked** — e.g., whether any installer/onboarding flow (`chuzom-onboard`, `chuzom-quickstart`) ever sets `CHUZOM_GATEWAY_HOST` or selects the `team-server` preset by default or via a "recommended for teams" prompt without equally strongly recommending a network boundary (firewall/reverse-proxy/VPN). If onboarding steers real users toward the `0.0.0.0` configuration more often than the file-level severity assessment (P1, "requires an explicit operator choice") assumes, the real-world severity is higher than assessed here.
3. **Whether `secrets_vault.py`'s pluggable-backend mechanism (`CHUZOM_SECRETS_BACKEND`, `register_backend()`) has any real non-env backend implementation anywhere in the dependency tree that persists keys to disk** — the module itself only ships `EnvSecretsVault` (no file I/O, so no file-permission question for THIS module), but `register_backend()` exists specifically to let something else plug in a real vault; if such a backend exists (e.g. in an enterprise/paid tier not present in this open-source tree, or a plugin package), its at-rest file permissions were never checked and remain a complete unknown.

---

## Verdict

**Is it safe to put Chuzom between a developer and their private repositories and credentials?**

Conditionally, and only for the default, single-user, loopback-only configuration — not as broadly as the product's positioning implies.

For the common case — one developer, default install, no `team-server` preset, no `CHUZOM_GATEWAY_HOST`, no `--host 0.0.0.0` anywhere — the network surface is genuinely closed by default, the admin API and dashboard have real, working authentication, and one real defense (structlog secret scrubbing) is correctly wired into the logging pipeline. That is a materially better security posture than "advisory theater everywhere," and it deserves to be said plainly: not every control in this codebase is decorative.

But the moment you use this product for its stated purpose of agentic execution against real repositories — `llm_act`/`llm_delegate` — you are exposed to a P0-severity prompt-injection passthrough (RED6-01) with a second, independently-provable P0 (RED6-02: full-environment subprocess inheritance) sitting right behind it. Together they mean: a hostile or merely careless repository — a poisoned README, a malicious dependency, a booby-trapped issue description — can currently cause the delegated agent to (a) receive instructions Chuzom's own injection detector correctly flags as suspicious and does nothing about, and (b) run those instructions in a shell that has every one of your API keys sitting in its environment, unfiltered. This is not a theoretical composition of two independent low-severity bugs; it is a single, direct, code-path-proven chain from "attacker controls text in your repo" to "attacker's chosen shell command has your Anthropic/OpenAI/whatever-else key in its environment." I would not run `llm_act`/`llm_delegate` against a repository I did not already fully trust, today, at this SHA.

Separately, the moment you use the product's own advertised team-sharing feature (the `team-server` preset), you reintroduce — in a currently-shipping, currently-documented code path — the exact vulnerability class (`0.0.0.0`, no auth) that this same codebase has an entire historical security notice about having removed once already (SEC-001). The fix pattern for it already exists in this codebase (`server.py`'s `_allow_public_bind()`); it simply wasn't applied to the two components (`gateway.py`, `route_server.py`) that needed it.

The recurring theme across all three P0/P1 findings is the same: this team clearly knows how to build the right control (the injection detector exists and is correctly used elsewhere; the env-scrubbing subprocess wrapper exists and works elsewhere; the public-bind refusal gate exists and works elsewhere) — but has not consistently wired those controls to every place they're needed, and has no integration tests that would have caught the gap. Every one of the P0/P1 findings in this report is "the lock exists, it's just not on this door." That is fixable, and probably fixable fast, but it is not fixed today.
