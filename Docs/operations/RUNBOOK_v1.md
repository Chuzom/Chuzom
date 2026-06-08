# Operator Runbook v1 — Install, Upgrade, Rollback, Secret Rotation

**Audience.** Platform / infra engineers responsible for chuzom on a workstation fleet or a small self-hosted instance. Single-process deployments only — multi-instance and HA scenarios are deferred to RUNBOOK v3 (Track 5 in `docs/audit/post-remediation/GAP_ANALYSIS.md`).

**Scope.** This runbook covers the four most-common operational tasks. v2 will add model/provider retirement, debug-a-routing-decision, and SIEM export. v3 will add emergency-kill and incident-response.

**Status of this document.** First operator-facing runbook in the chuzom repo. Anything not explicitly documented here is either (a) automated by an installed CLI or (b) an explicit known gap from `GAP_ANALYSIS.md`.

---

## 0. Prerequisites

- Python **3.10 or newer**. Verify: `python3 --version` → `Python 3.10.x` or higher.
- `pip` (or `uv pip` / `uvx`) reachable on `PATH`.
- Write access to the user's home directory (`~/.chuzom/`, `~/.claude/`).
- Provider API keys ready for whichever providers will be used. At minimum **one** of:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
  - `GEMINI_API_KEY`
  - `DEEPSEEK_API_KEY`
  - `OPENROUTER_API_KEY`

For an offline / air-gapped install, you also need a built wheel (`chuzom_router-X.Y.Z-py3-none-any.whl`) and the wheels of its runtime dependencies. The air-gapped path is documented in §1.3.

---

## 1. Install

### 1.1 From PyPI (recommended)

```bash
# Install or upgrade the router itself.
pip install --upgrade chuzom-router

# Verify the CLI surface.
which chuzom              # expect: a path inside the active venv/system
chuzom --version          # expect: 0.2.0 or higher

# Run the doctor to surface configuration / permission issues.
chuzom doctor
```

The four console scripts that ship today are:

| Script | Purpose |
|---|---|
| `chuzom` | Stdio MCP server entry point |
| `chuzom-onboard` | Interactive wizard for provider keys + profile |
| `chuzom-install-hooks` | Install Claude Code hooks into `~/.claude/` |
| `chuzom-quickstart` | One-shot wizard that calls the three above in sequence |

Note: `chuzom-sse` is **not** installed. Removed in v0.2.0 per SEC-001 (the prior SSE entry point bound `0.0.0.0` with no auth). Do not attempt to re-introduce SSE without an auth-middleware wrapper. See `Docs/audit/FINDINGS.md` F-SEC-001.

### 1.2 Interactive onboarding

```bash
chuzom-onboard
```

This wizard:

1. Reads any existing `.env` in the current directory.
2. Prompts to add or update provider API keys (Gemini / OpenAI / Anthropic / DeepSeek / OpenRouter).
3. Selects a routing profile (`budget` / `balanced` / `premium`).
4. Writes the final `.env`.

For unattended installs, set the relevant env vars before running anything (skip the wizard):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GEMINI_API_KEY="..."
# Optional identity (Tier 1/2 audit attribution):
export CHUZOM_USER_ID="alice@corp.io"
export CHUZOM_USER_EMAIL="alice@corp.io"
export CHUZOM_ORG_ID="acme"
# Optional agent attribution (Tier 2):
export CHUZOM_AGENT_ID="agno-reviewer"
```

### 1.3 Air-gapped install from wheel

```bash
# On a host with network access:
pip download chuzom-router -d ./chuzom-bundle
# Copy ./chuzom-bundle to the air-gapped host, then:
pip install --no-index --find-links=./chuzom-bundle chuzom-router
```

### 1.4 Wire into Claude Code (optional)

```bash
chuzom-install-hooks
# Installs hooks under ~/.claude/hooks/ and registers them in ~/.claude/settings.json.
```

### 1.5 Post-install verification

```bash
# 1. Tool surface (default-installed binaries):
ls "$(python3 -c 'import sys; print(sys.prefix)')/bin/chuzom"*
# Expect: chuzom, chuzom-install-hooks, chuzom-onboard, chuzom-quickstart
# Do NOT expect: chuzom-sse

# 2. Configuration sanity:
chuzom doctor

# 3. End-to-end smoke (requires at least one provider key set):
chuzom -c "say hi" || echo "smoke failed — check chuzom doctor output"
```

### 1.6 Where chuzom puts things

| Path | Purpose | Backup-worthy? |
|---|---|---|
| `~/.chuzom/usage.db` | Per-call cost / latency / tokens (SQLite) | **Yes** — Finance reconciliation source |
| `~/.chuzom/audit.db` | Tamper-evident audit chain (SQLite) | **Yes** — compliance source |
| `~/.chuzom/routing_lineage.db` | Lineage analytics (SQLite) | Optional |
| `~/.chuzom/routing_lineage.jsonl` | JSONL sidecar of the above | Optional |
| `~/.chuzom/profile.yaml` | Auto-detected provider profile | Regenerable via `chuzom-onboard` |
| `~/.chuzom/last_classification_<sid>.json` | Per-session classification shard (INV-007) | No — ephemeral |
| `~/.claude/hooks/chuzom-*.py` | Hook bridges to Claude Code | Regenerable via `chuzom-install-hooks` |

---

## 2. Upgrade

### 2.1 The default flow

```bash
# 1. Snapshot what's running NOW. You'll need this for rollback.
chuzom --version | tee /tmp/chuzom.preupgrade.version
cp ~/.chuzom/usage.db ~/.chuzom/usage.preupgrade.db
cp ~/.chuzom/audit.db ~/.chuzom/audit.preupgrade.db

# 2. Upgrade.
pip install --upgrade chuzom-router

# 3. Re-run doctor — surfaces any post-upgrade migration issues.
chuzom doctor

# 4. Refresh the Claude Code hook installation (chuzom auto-updates hooks
#    at MCP server boot, but explicit is better for an upgrade).
chuzom-install-hooks
```

### 2.2 Database migrations

chuzom auto-migrates SQLite schemas on the first connection after upgrade. There are two parallel tracks:

- **`enterprise/audit.py`** — append-only; new columns added via `ALTER TABLE` are idempotent.
- **`lineage/lineage_store.py`** — same; the v0.2.0 lineage rewrite (`docs/audit/post-remediation/REMEDIATION_VERIFICATION.md` notes the `LineageStore.__init__` dual-keyword constructor change).

Verify after upgrade:

```bash
sqlite3 ~/.chuzom/audit.db "PRAGMA integrity_check;"
# Expect: ok

sqlite3 ~/.chuzom/audit.db "SELECT COUNT(*) FROM audit_events;"
# Expect: same or higher than pre-upgrade snapshot
```

### 2.3 If a migration fails

Symptom: `chuzom doctor` reports a schema mismatch, or the MCP server logs `sqlite3.OperationalError` at boot.

```bash
# Don't keep using a half-migrated DB.
mv ~/.chuzom/audit.db ~/.chuzom/audit.failed-migration.db
# The next chuzom invocation will create a fresh audit chain.
# Recover by:
#   - rolling back chuzom (§3)
#   - OR restoring from your snapshot (cp ~/.chuzom/audit.preupgrade.db ~/.chuzom/audit.db)
#   - then opening a bug with the failed-migration DB attached.
```

**Hash-chain implication.** A re-created audit DB starts a new chain. The old chain remains intact in the snapshot; any compliance review must consider both. See `enterprise/audit.py::verify_chain` for the per-chain integrity check.

---

## 3. Rollback

### 3.1 Code rollback

```bash
# Reinstall the prior version (use the version captured in §2.1).
pip install --upgrade "chuzom-router==<PRIOR_VERSION>"
chuzom --version  # verify
```

### 3.2 Audit + usage DB rollback

If the upgrade migrated the DB schema in a way you need to back out:

```bash
# Stop any running chuzom processes first.
pkill -f "chuzom"  # or your process manager's equivalent

# Restore from snapshot.
cp ~/.chuzom/usage.preupgrade.db ~/.chuzom/usage.db
cp ~/.chuzom/audit.preupgrade.db ~/.chuzom/audit.db
```

### 3.3 Verify rollback

```bash
chuzom doctor
sqlite3 ~/.chuzom/audit.db "PRAGMA integrity_check;"   # expect: ok
chuzom -c "say hi"                                     # expect: successful response
```

### 3.4 Important rollback caveats

- **Hooks.** If you rolled back across a version that bundled new hook scripts, run `chuzom-install-hooks` again so the installed hooks match the running version.
- **Hash chain.** Any audit rows written *between* the snapshot and the rollback are lost. They live only in the upgrade-time DB you replaced. Preserve that file (`~/.chuzom/audit.failed-migration.db`) for compliance review.
- **Open MCP clients.** Claude Code / Cursor / etc. may keep a stale MCP-server process. Restart them after rollback or rely on Claude Code's auto-relaunch (most hosts will spawn a fresh server within ~30 s).

---

## 4. Secret rotation

chuzom does not yet broker provider keys (G-005 — SSO/SCIM is a Q-P-2-gated Phase-3 item). Today, **provider keys live in the operator's env or `.env` file**. Rotation is therefore an env-level action; the platform team's secret-management tooling (Vault, AWS SSM, 1Password CLI, etc.) is the source of truth.

### 4.1 Rotate one provider key

```bash
# 1. Issue a new key from the provider console.
# 2. Roll it into the operator's env / .env. Example for OpenAI:
export OPENAI_API_KEY="sk-NEW-..."

# 3. If the key lives in ~/.chuzom/.env or a project .env, update that file too.
#    Use atomic replace to avoid partial reads:
TMPFILE=$(mktemp)
sed 's/^OPENAI_API_KEY=.*/OPENAI_API_KEY=sk-NEW-.../' .env > "$TMPFILE" && mv "$TMPFILE" .env

# 4. Restart any chuzom processes so the env is re-read.
pkill -f "chuzom"  # or your process manager's equivalent

# 5. Verify the new key is reachable.
chuzom doctor
chuzom -c "say hi"  # picks the first available provider; should use the new key.

# 6. After confirming success, revoke the OLD key in the provider console.
```

### 4.2 Rotate the Agoragentic credential (SEC-003-gated)

If `CHUZOM_AGORAGENTIC=on` is set, `~/.chuzom/agoragentic.json` holds the marketplace API key.

```bash
# 1. Re-register the agent in the Agoragentic console; capture the new api_key + id.
# 2. Replace the credential file. Atomic:
TMPFILE=$(mktemp)
jq --arg k "NEW-API-KEY" --arg i "agent-id" '{api_key: $k, id: $i}' > "$TMPFILE"
mv "$TMPFILE" ~/.chuzom/agoragentic.json
chmod 600 ~/.chuzom/agoragentic.json
# 3. Restart any chuzom processes (the credential is cached in-process).
pkill -f "chuzom"
```

### 4.3 What `chuzom doctor` checks

`chuzom doctor` walks every provider you have a key for and reports:

- Whether the key is set / loaded.
- Whether the API responds to a low-cost probe.
- Circuit-breaker state per provider.
- Audit-chain freshness (`last_classification_*.json` mtime).

Run it after every rotation. If a provider does not turn green within ~60 s of rotation, the rotation has not fully propagated (env vs. `.env` mismatch; cached `.env`; cron-launched chuzom process inheriting stale env; etc.).

### 4.4 Things this runbook does **not** cover (yet)

The following are explicit gaps from `docs/audit/post-remediation/GAP_ANALYSIS.md` and will be added once their code lands:

| Gap | Documented in | Will appear in |
|---|---|---|
| Identity broker / SSO / SCIM | G-005 | RUNBOOK v3 |
| Central provider-key vault | G-004 | RUNBOOK v3 |
| Emergency kill switch (kill a model / provider / agent without restart) | G-007 + Track 3 | RUNBOOK v3 |
| SIEM export pipeline operation | G-010 | RUNBOOK v2 |
| Cost reconciliation against provider invoices | G-006 | RUNBOOK v2 |

---

## 5. Quick-reference: common failures and where to look

| Symptom | Most likely cause | First action |
|---|---|---|
| `chuzom doctor` says "no providers reachable" | All keys missing or invalid | Re-run §4.1 for each provider |
| Long latency on `chuzom -c "..."` | Cold-start fsync on `~/.chuzom/audit.db` (first turn after a clean install) | Run a second turn; check `chuzom dashboard` for steady-state latency |
| `verify_chain()` failure | DB written by a stopped process and an external editor; OR rollback restored an older chain | §3.4 hash-chain caveats |
| `audit_routing_turn` warnings in logs | Disk full; permissions; `~/.chuzom/audit.db` missing | Confirm disk + permissions; remove the DB and let it recreate (chain restart) |
| `chuzom-sse` missing | **Expected** — removed in v0.2.0 (SEC-001). Use stdio (`chuzom`) until a hardened SSE wrapper ships |
| `CostBudgetExceeded` exception | Caller set `max_cost_per_task` and no model fit the cap | Either raise the cap, allow a cheaper model, or accept the deny |
| `WallClockExceeded` exception | Caller set `max_wall_clock_seconds` and the chain didn't return in time | Raise the cap, or investigate provider latency via `chuzom doctor` |

---

## 6. Changelog for this runbook

| Version | Date | Notes |
|---|---|---|
| v1 | 2026-06-08 | First runbook. Install, upgrade, rollback, secret rotation. Single-process scope. |

---

## 7. Where this runbook lives in the bigger plan

This document closes **T5-S1** from `docs/audit/post-remediation/GAP_ANALYSIS.md` G-018 (operator runbook gap). It does NOT close G-018 — that requires v2 + v3 too. The progression:

- **v1 (this document)** — install / upgrade / rollback / secret rotation
- **v2** — model & provider retirement, debug-a-routing-decision, SIEM export
- **v3** — emergency kill, incident response, multi-instance operation

Each subsequent volume depends on engineering work landing first (full G-list in `docs/audit/post-remediation/GAP_ANALYSIS.md`).
