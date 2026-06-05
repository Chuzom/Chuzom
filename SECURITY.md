# Security Policy

> Tessera is a routing layer that sits between developer prompts and LLM
> providers. It handles secrets (provider API keys), processes potentially
> sensitive prompts, and writes audit-grade logs. This document covers what
> Tessera does to protect those flows and how to report security issues.

## Reporting a vulnerability

If you find a vulnerability, **please do not open a public issue.**

Email **ypollak2@users.noreply.github.com** with:
- A description of the issue and its impact
- Steps to reproduce (proof-of-concept welcome)
- Affected Tessera version (`tessera --version`)
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
| 0.0.x (current dogfood) | ✅ | All releases |
| Pre-fork llm-router | ⚠️ | Use Tessera; llm-router gets best-effort |

Production users should upgrade to the latest 0.0.x release. v0.1.0 (the
public-ring release) is the first version with a formal LTS commitment.

## Security posture

### Secrets handling

- **Provider API keys** are never stored in the Tessera database. They live in:
  - Environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...)
  - `~/.tessera/config.yaml` (mode-600 user-readable; for security-policy
    deployments that block .env files)
  - For enterprise: `${vault:...}` / `${aws-sm:...}` / `${gcp-sm:...}`
    indirections in `OrgPolicy` YAML; resolution happens at request time
- **API tokens issued by Tessera** are stored as SHA-256 hashes only. The
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

- **All state lives in `~/.tessera/`** by default (5 SQLite databases):
  - `lineage.db` — every routing decision (privacy-safe prompt
    fingerprints, NOT raw prompts)
  - `sessions.db` — agent session lifecycle
  - `identity.db` — users + teams + tokens
  - `audit.db` — immutable audit chain
  - `quotas.db` — per-identity consumption + policies
- **Override locations** per database via `TESSERA_LINEAGE_PATH`,
  `TESSERA_SESSIONS_PATH`, `TESSERA_IDENTITY_PATH`, `TESSERA_AUDIT_PATH`,
  `TESSERA_QUOTAS_PATH`.
- **No telemetry** sent to Tessera maintainers. The only outbound traffic
  is to configured LLM providers + (optionally) the OTLP endpoint.

### Network security

- **TLS** for all provider API calls (handled by `litellm`).
- **Egress allowlist** (v0.0.3): planned. Today, providers Tessera will
  talk to are determined by which API keys are configured.
- **OTLP**: gRPC or HTTP exporter — uses TLS when endpoint is `https://`
  or when standard `OTEL_EXPORTER_OTLP_INSECURE=false`.

### Dependency posture

- **Direct dependencies** declared in `pyproject.toml` with lower bounds.
- **Lock file** (`uv.lock`) pins transitive versions.
- **Security extras**: `tessera-router[secrets-vault]`, `[secrets-aws]`,
  `[secrets-gcp]`, `[tracing]` — installed only when needed, reducing
  attack surface for users who don't need them.
- **Plaintext credentials** in source / config caught by:
  1. `tessera.signals.pii.PiiSignal` at prompt-routing time
  2. `tessera.org_policy._scan_for_plaintext_secrets` at policy-load time
  3. `tessera.enterprise.redaction.redact_prompt` at lineage-write time

## Threats explicitly NOT in scope

These are valid concerns but the project does not currently mitigate them.
Listed honestly so users can layer their own controls:

- **Host compromise**: if an attacker has read access to `~/.tessera/`,
  they can read your lineage and (in production) your agent session state.
  Token hashes are useless to an attacker but the lineage contains
  prompt fingerprints + cost data.
- **Provider-side breaches**: Tessera cannot defend against OpenAI /
  Anthropic / Google having their own incidents.
- **Side-channel attacks** on the routing decisions themselves: timing
  signals from which provider was chosen are not currently obfuscated.
- **Multi-tenant isolation**: v0.0.2 assumes a single-org deployment. The
  schema is forward-compatible with multi-tenancy but the auth layer
  doesn't currently isolate org_id across requests.

## Compliance mapping

Tessera provides primitives that map cleanly to common compliance
controls. **Tessera is not certified** for any of these regimes; the
mapping below is to help your security team build the case.

| Control | Tessera primitive |
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
