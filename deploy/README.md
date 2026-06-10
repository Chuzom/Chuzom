# Deploying chuzom (E3)

Three ways to run chuzom as a long-lived service. All use the new
`chuzom serve` entrypoint (secured SSE MCP server with Bearer/OIDC auth;
`chuzom serve --admin` runs the FastAPI admin control plane instead).

> Binding `0.0.0.0` requires `CHUZOM_SSE_ALLOW_PUBLIC=on` — a deliberate safety
> gate so a careless deployment can't expose the routing surface without auth.

## 1. Docker

```bash
docker build -t chuzom-router:local .
docker run --rm -p 17891:17891 \
  -e CHUZOM_DEPLOYMENT_PROFILE=enterprise \
  -e CHUZOM_SSE_ALLOW_PUBLIC=on \
  -e OPENAI_API_KEY=sk-... \
  chuzom-router:local
```

## 2. docker-compose (router + Postgres budget backend)

The "try enterprise mode in two minutes" stack — secured SSE server +
multi-instance Postgres budget backend (T2-XL1).

```bash
cp .env.example .env   # add provider keys / OIDC config
docker compose up --build
```

## 3. Kubernetes (Helm)

```bash
helm install chuzom deploy/helm/chuzom \
  --set image.tag=local \
  --set secrets.OPENAI_API_KEY=sk-... \
  --set oidc.issuer=https://idp.example.com \
  --set oidc.audience=chuzom \
  --set ingress.enabled=true --set ingress.host=chuzom.example.com --set ingress.tls=true
```

Prefer an external secrets operator over `--set` for production keys. See
`deploy/helm/chuzom/values.yaml` for all knobs (replicas, budget backend,
quota mode, resources, ingress/TLS).

## 4. systemd (VM)

```bash
sudo useradd --system --create-home --home-dir /var/lib/chuzom chuzom
sudo pip install chuzom-router    # or pipx; ensure `chuzom` is on PATH
sudo install -d /etc/chuzom
sudo cp deploy/systemd/chuzom.service /etc/systemd/system/
# Create /etc/chuzom/chuzom.env with CHUZOM_SSE_ALLOW_PUBLIC=on + provider keys
sudo systemctl daemon-reload && sudo systemctl enable --now chuzom
```

## Air-gapped (Ollama-only)

chuzom runs fully offline with no cloud egress at startup: set
`OLLAMA_BASE_URL`, omit all cloud provider keys, and the router uses local
models only. `chuzom doctor` / `chuzom verify-enterprise` validate the posture
without network access.
