# syntax=docker/dockerfile:1
# chuzom — deployable image (E3). Multi-stage: build a venv with uv, then copy
# it into a slim runtime. Runs as a non-root user; default entrypoint is the
# secured SSE MCP server (Bearer/OIDC auth).

# ── Builder ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached layer), then the project. The sso/postgres/
# tracing extras cover enterprise deployments (OIDC + multi-instance + OTel).
COPY pyproject.toml README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install ".[sso,postgres,tracing]"

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root runtime user; state dir owned by it.
RUN useradd --create-home --uid 10001 chuzom \
    && mkdir -p /home/chuzom/.chuzom \
    && chown -R chuzom:chuzom /home/chuzom/.chuzom

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/home/chuzom \
    # Enterprise-safe defaults for a deployed service.
    CHUZOM_DEPLOYMENT_PROFILE=enterprise \
    CHUZOM_LOG_JSON=1 \
    CHUZOM_SSE_ALLOW_PUBLIC=on

USER chuzom
WORKDIR /home/chuzom

EXPOSE 17891

# P1-4: TCP healthcheck on the SSE listen port. The SSE app has no
# unauthenticated HTTP /health route, so a successful TCP connect is the honest
# liveness signal. Uses python (already in the image) — no curl dependency.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import socket,sys; sys.exit(0) if socket.create_connection(('127.0.0.1', 17891), 3) else sys.exit(1)" || exit 1

# The SSE server refuses 0.0.0.0 without CHUZOM_SSE_ALLOW_PUBLIC=on (set above).
# Override the command for the admin API: `chuzom serve --admin --host 0.0.0.0`.
ENTRYPOINT ["chuzom", "serve", "--host", "0.0.0.0", "--port", "17891"]
