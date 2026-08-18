"""Central registry of every environment variable this codebase reads.

RED8-10. 195 distinct variables are read across 313 sites, and nothing declared
them. A config surface nobody has enumerated cannot be documented, cannot be
validated, and drifts silently -- the audit counted 186; by the time it was
measured here it was 195, and no one had noticed the difference.

WHY THIS IS A CHECKED-IN LITERAL AND NOT GENERATED
--------------------------------------------------
The obvious implementation is to walk the AST at import time and build this dict
from what the code actually reads. That would be worthless. The test that
validates the registry ALSO walks the AST, so a generated registry validates
against itself and passes unconditionally -- exactly the trap this audit has
already found twice:

  * ``tool_surface.unregistered()`` checked tier constants against ``_TIERS``,
    which IS the tier constants. A bogus tool name passed lint and 106 tests.
  * ``lint_tool_surface.py`` checks emitters against emitters, and reports clean
    under the same mutation.

Both LOOKED like validation. So this literal is the DECLARATION and the AST scan
is INDEPENDENT ground truth; the test compares them. Adding a new
``os.environ.get("X")`` fails that test until someone declares X here, which is
the entire point -- the friction is the feature.

CATEGORIES
----------
``chuzom``              this project's own configuration
``provider_credential`` third-party API keys and tokens -- never log these
``external_tool``       config for tools we shell out to or integrate with
``platform``            OS/terminal conventions (HOME, NO_COLOR, ...)
``test_only``           set by the test runner; must not affect production paths
"""

from __future__ import annotations

__all__ = ["ENV_REGISTRY", "CATEGORIES", "registered_names", "category_of"]

CATEGORIES = frozenset(
    {"chuzom", "provider_credential", "external_tool", "platform", "test_only"}
)

#: name -> (category, first_module_that_reads_it, module_count_at_registration)
ENV_REGISTRY: dict[str, tuple[str, str, int]] = {
    # ── chuzom  (152) ──
    "CHUZOM_ADMIN_ACTIONS_PATH": ("chuzom", "admin_actions.py", 1),
    "CHUZOM_AGENTIC_MODEL": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_AGENTS_CONFIG": ("chuzom", "tools/agents.py", 1),
    "CHUZOM_AGENT_POLICY_MODE": ("chuzom", "router.py", 1),
    "CHUZOM_AGENT_ROUTE_ALLOW": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_ALERT_WEBHOOK": ("chuzom", "alerts.py", 1),
    "CHUZOM_ALLOWED_HOSTS": ("chuzom", "route_server.py", 1),
    "CHUZOM_ALLOW_STUBS": ("chuzom", "cost.py", 2),
    "CHUZOM_ALLOW_SUBAGENTS": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_ANOMALY_THRESHOLD": ("chuzom", "session_spend.py", 1),
    "CHUZOM_AUDIT_DISABLED": ("chuzom", "commands/verify_enterprise.py", 1),
    "CHUZOM_AUDIT_PATH": ("chuzom", "enterprise/audit.py", 1),
    "CHUZOM_BANDIT": ("chuzom", "router.py", 1),
    "CHUZOM_BASH_COMPRESS": ("chuzom", "hooks/bash-compress.py", 1),
    "CHUZOM_BENCHMARK_TTL_DAYS": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_BLOCK_PROVIDERS": ("chuzom", "router.py", 1),
    "CHUZOM_BOUNDED_OPERATIONAL": ("chuzom", "bounded_operational.py", 1),
    "CHUZOM_BROKER_CONCURRENCY": ("chuzom", "session_broker.py", 1),
    "CHUZOM_BROKER_SECRET_FILE": ("chuzom", "session_broker.py", 1),
    "CHUZOM_BROKER_SOCK": ("chuzom", "session_broker.py", 1),
    "CHUZOM_BUDGETS_DB_PATH": ("chuzom", "budget_backend.py", 1),
    "CHUZOM_BUDGET_BACKEND": ("chuzom", "budget_backend.py", 1),
    "CHUZOM_BUDGET_FORECAST_HORIZON_SECONDS": ("chuzom", "budget_backend.py", 1),
    "CHUZOM_BUDGET_FORECAST_MODE": ("chuzom", "budget_backend.py", 1),
    "CHUZOM_BUDGET_FORECAST_WINDOW_SECONDS": ("chuzom", "budget_backend.py", 1),
    "CHUZOM_BUDGET_POSTGRES_DSN": ("chuzom", "budget_backend_postgres.py", 1),
    "CHUZOM_CAPABILITY_ROUTING": ("chuzom", "capabilities.py", 1),
    "CHUZOM_CLASSIFY_LOCAL_ONLY": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_CLAUDE_SUBSCRIPTION": ("chuzom", "commands/demo.py", 6),
    "CHUZOM_CLAUDE_TIMEOUT": ("chuzom", "claude_agent.py", 1),
    "CHUZOM_CODEX_BASELINE": ("chuzom", "cost.py", 1),
    "CHUZOM_CODEX_MODELS": ("chuzom", "codex_agent.py", 1),
    "CHUZOM_COMPRESS_RESPONSE": ("chuzom", "tools/text.py", 1),
    "CHUZOM_CONFIDENCE_THRESHOLD": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_CONTEXT_OPTIMIZER": ("chuzom", "context.py", 1),
    "CHUZOM_CP_AUDIT_PATH": ("chuzom", "control_plane/audit.py", 1),
    "CHUZOM_CP_POSTGRES_DSN": ("chuzom", "control_plane/store_postgres.py", 1),
    "CHUZOM_CP_STORE_PATH": ("chuzom", "commands/cp.py", 2),
    "CHUZOM_DB_PATH": ("chuzom", "agentic/telemetry.py", 2),
    "CHUZOM_DELEGATE": ("chuzom", "hooks/enforce-route.py", 1),
    "CHUZOM_DEPLOYMENT_PROFILE": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_DEV_SRC": ("chuzom", "commands/dev_refresh.py", 1),
    "CHUZOM_DIRECT_EXECUTION": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_DISABLE_CONTINUATION_BYPASS": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_DISABLE_LLM_CLASSIFIERS": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_DISABLE_SUBPROCESS_BACKENDS": ("chuzom", "router.py", 1),
    "CHUZOM_DYNAMIC_LEADERBOARD_ORDERING": ("chuzom", "dynamic_routing.py", 1),
    "CHUZOM_ENFORCE": ("chuzom", "commands/doctor.py", 9),
    "CHUZOM_ENSEMBLE": ("chuzom", "ensemble.py", 1),
    "CHUZOM_ENSEMBLE_PRIMARY": ("chuzom", "ensemble.py", 1),
    "CHUZOM_ENSEMBLE_TIMEOUT": ("chuzom", "ensemble.py", 1),
    "CHUZOM_ESCALATE_DEADLINE_S": ("chuzom", "router.py", 1),
    "CHUZOM_ESCALATE_ON_QUALITY": ("chuzom", "router.py", 1),
    "CHUZOM_ESCALATE_THRESHOLD": ("chuzom", "router.py", 1),
    "CHUZOM_EXECUTION_LEDGER_DB": ("chuzom", "execution_ledger.py", 1),
    "CHUZOM_EXPLAIN": ("chuzom", "tools/routing.py", 2),
    "CHUZOM_FORCE_COLOR": ("chuzom", "surface_status.py", 1),
    "CHUZOM_FREE_TIER_DRAFTS": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_GATES": ("chuzom", "gates.py", 1),
    "CHUZOM_GATEWAY_HOST": ("chuzom", "presets.py", 1),
    "CHUZOM_GATEWAY_PORT": ("chuzom", "presets.py", 1),
    "CHUZOM_GATEWAY_URL": ("chuzom", "presets.py", 1),
    "CHUZOM_GEMINI_BASELINE": ("chuzom", "cost.py", 1),
    "CHUZOM_GEMINI_SUBSCRIPTION": ("chuzom", "commands/demo.py", 3),
    "CHUZOM_GEMINI_TIMEOUT": ("chuzom", "gemini_cli_agent.py", 1),
    "CHUZOM_HEALTH_SNAPSHOT": ("chuzom", "health.py", 1),
    "CHUZOM_HISTORY_RELAY": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_HOOK_SLOW_SECONDS": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_HTTP_TIMEOUT": ("chuzom", "hooks/session-end.py", 2),
    "CHUZOM_IDEMPOTENCY_PATH": ("chuzom", "idempotency.py", 1),
    "CHUZOM_IDENTITY_PATH": ("chuzom", "enterprise/identity.py", 1),
    "CHUZOM_INDICATOR": ("chuzom", "surface_status.py", 1),
    "CHUZOM_INVOICE_DISCREPANCY_PCT": ("chuzom", "invoice_reconciliation/__init__.py", 1),
    "CHUZOM_JUDGE_CASCADE_SAMPLE_RATE": ("chuzom", "judge_cascade.py", 1),
    "CHUZOM_JUDGE_CASCADE_THRESHOLD": ("chuzom", "judge_cascade.py", 1),
    "CHUZOM_JUDGE_MODEL": ("chuzom", "judge_cascade.py", 1),
    "CHUZOM_JUDGE_SAMPLE_RATE": ("chuzom", "judge.py", 1),
    "CHUZOM_LIBRARIAN_MODEL": ("chuzom", "library/sealer.py", 1),
    "CHUZOM_LOG_JSON": ("chuzom", "logging.py", 1),
    "CHUZOM_LOG_LEVEL": ("chuzom", "logging.py", 1),
    "CHUZOM_MAX_AGENT_DEPTH": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_METRICS_INCLUDE_PRESSURE": ("chuzom", "admin_api.py", 1),
    "CHUZOM_MINI_SUMMARY_EVERY": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_OIDC_AUDIENCE": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OIDC_DEFAULT_ORG": ("chuzom", "scim_api.py", 2),
    "CHUZOM_OIDC_DEFAULT_TEAM": ("chuzom", "scim_api.py", 2),
    "CHUZOM_OIDC_EMAIL_CLAIM": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OIDC_GROUPS_CLAIM": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OIDC_ISSUER": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OIDC_JWKS_URI": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OIDC_ROLE_MAP": ("chuzom", "enterprise/oidc.py", 1),
    "CHUZOM_OKF": ("chuzom", "okf.py", 1),
    "CHUZOM_OLLAMA_MODEL": ("chuzom", "hooks/auto-route.py", 3),
    "CHUZOM_OLLAMA_NUM_CTX": ("chuzom", "providers.py", 1),
    "CHUZOM_OLLAMA_TIMEOUT": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_OLLAMA_URL": ("chuzom", "hooks/agent_loop.py", 3),
    "CHUZOM_OLLAMA_WARMUP": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_OLLAMA_WARMUP_MODEL": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_PLAYWRIGHT_COMPRESS": ("chuzom", "hooks/playwright-compress.py", 1),
    "CHUZOM_POLICY": ("chuzom", "cli_init_policy.py", 2),
    "CHUZOM_POLICY_PATH": ("chuzom", "control_plane/migration.py", 1),
    "CHUZOM_POLICY_STORE_PATH": ("chuzom", "policy_versions.py", 1),
    "CHUZOM_PREMIUM_MAX_PRESSURE": ("chuzom", "router.py", 1),
    "CHUZOM_PRESET": ("chuzom", "presets.py", 1),
    "CHUZOM_PROFILE": ("chuzom", "commands/verify_enterprise.py", 3),
    "CHUZOM_PROJECT_DIR": ("chuzom", "semantic_cache.py", 1),
    "CHUZOM_PROVIDER_REGISTRY_PATH": ("chuzom", "provider_registry.py", 1),
    "CHUZOM_PXPIPE_ENABLED": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_PXPIPE_HEAVY_MODELS": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_PXPIPE_URL": ("chuzom", "hooks/session-start.py", 1),
    "CHUZOM_QUOTAS_PATH": ("chuzom", "enterprise/quotas.py", 1),
    "CHUZOM_QUOTA_DELAY": ("chuzom", "quota_tracker.py", 1),
    "CHUZOM_QUOTA_RETRY": ("chuzom", "quota_tracker.py", 1),
    "CHUZOM_QUOTA_TTL": ("chuzom", "hooks/auto-route.py", 2),
    "CHUZOM_RENDER_MODE": ("chuzom", "hooks/response_formatter.py", 1),
    "CHUZOM_RESPONSE_ROUTER": ("chuzom", "commands/doctor.py", 3),
    "CHUZOM_ROUTE_BANNER": ("chuzom", "hooks/agent-route.py", 2),
    "CHUZOM_ROUTING_LEDGER": ("chuzom", "routing_quality.py", 1),
    "CHUZOM_SCIM_ENABLED": ("chuzom", "scim_api.py", 1),
    "CHUZOM_SCIM_ROLE_MAP": ("chuzom", "scim_api.py", 1),
    "CHUZOM_SECRETS_BACKEND": ("chuzom", "secrets_vault.py", 1),
    "CHUZOM_SEMANTIC_CACHE_THRESHOLD": ("chuzom", "semantic_cache.py", 1),
    "CHUZOM_SEMANTIC_CENTROIDS": ("chuzom", "semantic_classify.py", 1),
    "CHUZOM_SEMANTIC_CLASSIFIER_BACKEND": ("chuzom", "semantic_classify.py", 1),
    "CHUZOM_SEMANTIC_ST_MODEL": ("chuzom", "semantic_classify.py", 1),
    "CHUZOM_SERVICE_PORT": ("chuzom", "hook_client.py", 3),
    "CHUZOM_SESSIONS_PATH": ("chuzom", "agents/session.py", 1),
    "CHUZOM_SESSION_BUDGET": ("chuzom", "hooks/enforce-route.py", 1),
    "CHUZOM_SESSION_CONTEXT": ("chuzom", "session_store.py", 1),
    "CHUZOM_SESSION_ID": ("chuzom", "hooks/auto-route.py", 2),
    "CHUZOM_SESSION_PAID_CAP": ("chuzom", "hooks/auto-route.py", 1),
    "CHUZOM_SIDECAR_PREFETCH": ("chuzom", "commands/doctor.py", 2),
    "CHUZOM_SLIM": ("chuzom", "tool_surface.py", 1),
    "CHUZOM_STALE_PRESSURE_FLOOR": ("chuzom", "budget.py", 1),
    "CHUZOM_STATE_DIR": ("chuzom", "surface_status.py", 1),
    "CHUZOM_STATUS_EVERY": ("chuzom", "hooks/status-bar-clawcode.py", 2),
    "CHUZOM_STATUS_MODE": ("chuzom", "hooks/status-bar.py", 1),
    "CHUZOM_STREAMING_JUDGE": ("chuzom", "streaming_judge.py", 1),
    "CHUZOM_SUBAGENT_CLI_DELEGATION": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBAGENT_CLI_TIMEOUT": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBAGENT_DIRECT": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBAGENT_DIRECT_MAX_COMPLEXITY": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBAGENT_GOVERNANCE": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBAGENT_MODEL_PIN": ("chuzom", "hooks/agent-route.py", 1),
    "CHUZOM_SUBPROCESS_TIMEOUT": ("chuzom", "hooks/session-end.py", 2),
    "CHUZOM_SUBSCRIPTION_USD_PER_MONTH": ("chuzom", "quota_savings.py", 1),
    "CHUZOM_SUPPRESS_PRICING_STALENESS": ("chuzom", "pricing.py", 1),
    "CHUZOM_URL": ("chuzom", "commands/doctor.py", 1),
    "CHUZOM_USAGE_DB_PATH": ("chuzom", "quota_savings.py", 1),
    "CHUZOM_USAGE_PATH": ("chuzom", "commands/invoice.py", 1),
    "CHUZOM_WEEKLY_QUOTA_USD": ("chuzom", "quota_savings.py", 1),
    "CHUZOM_WEEKLY_QUOTA_USD_OPUS_EQUIV": ("chuzom", "quota_savings.py", 1),
    "CHUZOM_ZERO_CLAUDE": ("chuzom", "hooks/auto-route.py", 2),
    # ── indirect reads: DECLARED BY HAND, invisible to the AST scan ──
    # These are read through a VARIABLE, not a string literal:
    #     for env in (ALLOW_PUBLIC_ENV, LEGACY_SSE_ALLOW_PUBLIC_ENV):
    #         os.environ.get(env)
    # The scanner matches os.environ.get("LITERAL") only, so it cannot see them —
    # and neither can any similar tool. Stated here rather than quietly omitted,
    # because a registry that silently under-reports its own surface is the same
    # class of defect as the guards this audit keeps finding: it looks complete.
    "CHUZOM_ALLOW_PUBLIC_BIND": ("chuzom", "net_bind.py", 1),
    "CHUZOM_SSE_ALLOW_PUBLIC": ("chuzom", "net_bind.py", 1),

    # ── provider_credential  (20) ──
    "ANTHROPIC_ADMIN_KEY": ("provider_credential", "invoice_reconciliation/anthropic.py", 1),
    "CHUZOM_CP_ED25519_PRIVATE_KEY": ("provider_credential", "control_plane/signing.py", 1),
    "CHUZOM_CP_SIDECAR_TOKEN": ("provider_credential", "control_plane/api.py", 1),
    "CHUZOM_ESCALATE_MIN_PROMPT_TOKENS": ("provider_credential", "router.py", 1),
    "CHUZOM_HF_TOKENIZERS": ("provider_credential", "token_budget.py", 1),
    "CHUZOM_PROJECT_ID": ("provider_credential", "session_store.py", 1),
    "CHUZOM_RESPONSE_ROUTER_TOKEN_THRESHOLD": ("provider_credential", "response_router.py", 1),
    "CHUZOM_SCIM_TOKEN": ("provider_credential", "admin_api.py", 2),
    "CHUZOM_TOKEN": ("provider_credential", "commands/verify_enterprise.py", 1),
    "DEEPSEEK_API_KEY": ("provider_credential", "commands/doctor.py", 1),
    "GEMINI_ACCESS_TOKEN": ("provider_credential", "invoice_reconciliation/gemini.py", 1),
    "GEMINI_API_KEY": ("provider_credential", "commands/demo.py", 7),
    "GEMINI_PROJECT_ID": ("provider_credential", "invoice_reconciliation/gemini.py", 1),
    "GOOGLE_API_KEY": ("provider_credential", "commands/demo.py", 3),
    "HELICONE_API_KEY": ("provider_credential", "integrations/helicone.py", 1),
    "OPENAI_ADMIN_KEY": ("provider_credential", "invoice_reconciliation/openai.py", 1),
    "OPENAI_API_KEY": ("provider_credential", "commands/demo.py", 7),
    "OPENROUTER_API_KEY": ("provider_credential", "commands/doctor.py", 1),
    "PERPLEXITY_API_KEY": ("provider_credential", "commands/demo.py", 1),
    "VAULT_TOKEN": ("provider_credential", "org_policy.py", 1),
    # ── external_tool  (19) ──
    "CLAUDE_CODE_PATH": ("external_tool", "claude_agent.py", 1),
    "CLAUDE_CODE_SESSION_ID": ("external_tool", "hooks/agent-depth-release.py", 3),
    "CLAUDE_SESSION_ID": ("external_tool", "hooks/context-capture.py", 6),
    "CODEX_PATH": ("external_tool", "codex_agent.py", 1),
    "GEMINI_CLI_PATH": ("external_tool", "gemini_cli_agent.py", 1),
    "GEMINI_CLI_TIER": ("external_tool", "gemini_cli_quota.py", 1),
    "HOST": ("external_tool", "server.py", 1),
    "LOCALAPPDATA": ("external_tool", "install_hooks.py", 1),
    "OLLAMA_BASE_URL": ("external_tool", "agentic/react.py", 8),
    "OLLAMA_BUDGET_MODELS": ("external_tool", "hooks/chain_builder.py", 1),
    "OLLAMA_HOST": ("external_tool", "hooks/playwright-compress.py", 1),
    "OLLAMA_URL": ("external_tool", "commands/doctor.py", 2),
    "OTEL_EXPORTER_OTLP_ENDPOINT": ("external_tool", "observability.py", 2),
    "OTEL_EXPORTER_OTLP_INSECURE": ("external_tool", "tracing.py", 1),
    "OTEL_SERVICE_NAME": ("external_tool", "observability.py", 2),
    "PORT": ("external_tool", "server.py", 1),
    "RESPONSE": ("external_tool", "hooks/response-router.py", 1),
    "VAULT_ADDR": ("external_tool", "org_policy.py", 1),
    "_SESSION_BUDGET_WARNING": ("external_tool", "hooks/enforce-route.py", 1),
    # ── platform  (3) ──
    "APPDATA": ("platform", "commands/doctor.py", 4),
    "NO_COLOR": ("platform", "commands/budget.py", 16),
    "XDG_CONFIG_HOME": ("platform", "install_hooks.py", 1),
    # ── test_only  (1) ──
    "PYTEST_CURRENT_TEST": ("test_only", "config.py", 4),
}


def registered_names() -> frozenset[str]:
    return frozenset(ENV_REGISTRY)


def category_of(name: str) -> str | None:
    entry = ENV_REGISTRY.get(name)
    return entry[0] if entry else None
