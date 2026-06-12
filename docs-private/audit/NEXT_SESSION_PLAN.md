# Next-Session Build Plans — Control-Plane Tracks

> Paste-ready specs for the two largest remaining enterprise-audit tracks.
> Authored 2026-06-10 alongside PR #54 (OIDC + SCIM). Run each in a **fresh
> `/clear`'d session** — the plans are self-contained.
>
> **Standing instructions for any session executing these:** work directly with
> native tools (Read/Edit/Write/Bash). Do NOT route the implementation through
> chuzom `llm_*` tools — codebase modification is the documented exception. If a
> chuzom PreToolUse hook blocks a write, clear it with one `llm_query("OK")` call
> and proceed. Read the real signatures before editing; assume nothing.

Contents:
1. [SSO follow-ups](#1-sso-follow-ups-finish-pr-54-track) — finish the OIDC/SCIM track
2. [F1–F5 control-plane wiring](#2-f1f5--control-plane-wiring) — audit Pillar 5: 48→78
3. [F5 admin-API test fixtures](#3-f5-admin-api-test-fixtures-paste-ready) — paste-ready

---

## 1. SSO follow-ups (finish the PR #54 track)

PR #54 shipped OIDC JWT validation + JIT provisioning + routing/middleware wiring
+ SCIM 2.0 CRUD (33 tests). Three follow-ups remain, none blocking:

- **Keycloak/Testcontainer e2e** — one `@pytest.mark.integration` test (skipped
  when Docker is absent) proving real OIDC discovery + JWKS fetch against a live
  IdP. The hermetic unit tests already cover the validation logic; this proves
  the network/discovery wiring only.
- **Mount `scim_api` into the admin app** — today `chuzom.scim_api.create_scim_app`
  is a standalone factory (testable, mountable). Mount its router into the main
  admin API under `CHUZOM_SCIM_ENABLED`, sharing the process `IdentityStore`.
- **Docs** — flip the README "What makes Chuzom different" comparison-table row
  `SSO / OIDC / SCIM` from `—` to `🟡` (footnote: "OIDC JWT + SCIM 2.0; SAML via
  OIDC bridge"); add a Keycloak/Okta/Entra worked example (issuer, audience,
  group→role map, SCIM token) to `Docs/ENTERPRISE_DEPLOYMENT.md`.

Reference patterns already in the tree (PR #54):
- OIDC JWT test fixture (local RSA key + injected JWKS, no network):
  `tests/test_oidc_validation.py`.
- SCIM HTTP test (FastAPI TestClient + bearer auth + `check_same_thread=False`):
  `tests/test_scim_provisioning.py`.

---

## 2. F1–F5 — Control-Plane Wiring

**Framing.** The enterprise control plane is BUILT but partially UNWIRED. The
audit's core finding is "implemented, enforced only under
`CHUZOM_PROFILE=enterprise`, and not always invoked on the routing path." So
F1–F5 is mostly **wire + prove-by-default + complete the admin stubs**, NOT
build-from-scratch. Some is already done (G-001 RBAC default-flip and G-003
audit-disable-refusal were verified present). FIRST assess what's live, THEN
change only the gaps. Every acceptance check is "enforced-by-default + proven-in-
a-test," never "code exists."

### STEP 0 — Assess current wiring (read before editing)
Read and note the REAL state of each:
- `src/chuzom/router.py` → `route_and_call`. Is `current_identity()` called per
  turn? Is an audit row written per turn (cached AND cold)? Is any quota check
  invoked? Grep: `current_identity`, `AuditLog`, `audit`, `quota`, `record`.
- `src/chuzom/identity.py` → `current_identity` / `_enterprise_identity`
  (OIDC-aware after PR #54).
- `src/chuzom/rbac_routing.py` → `_rbac_mode()` (strict under enterprise?),
  enforcement point + `PermissionDenied` raise.
- `src/chuzom/audit_routing.py` → audit gating; `CHUZOM_AUDIT_DISABLED` refused
  under enterprise?
- `src/chuzom/enterprise/audit.py` → `AuditLog.append` / `verify_chain` / event
  types / export.
- `src/chuzom/enterprise/quotas.py` + `src/chuzom/quota_balance.py` →
  `QuotaTracker` API (check, consume, caps).
- `src/chuzom/profile.py` → `is_enterprise()`.
- `src/chuzom/commands/verify_enterprise.py` → enterprise preflight verifier.
- `src/chuzom/admin_api.py` → which endpoints return 501 today.
- Existing tests: `test_tier1_audit_per_turn.py`, `test_t1_m2_rbac_route_prompt.py`,
  `test_t4_*quota*`, `test_admin_api_skeleton.py`, `test_enterprise_*.py`.

Write a 6-line "current vs target" note per F-item before touching code.

### F1 — Identity resolved + attributed on EVERY routed turn
Goal: every turn (cached hit and cold) carries `current_identity()` attribution
into the audit/lineage row.
- In `route_and_call`, resolve `current_identity()` once near entry and thread it
  into the lineage/audit write — including cached-response and early-return
  branches (the audit flagged cached turns as the likely gap).
- Under enterprise profile a failed resolution must raise
  `EnterpriseIdentityRequired` (the existing contract) — do NOT swallow it.
- Test (`test_f1_identity_on_every_turn.py`): a cached-hit turn and a cold turn
  both produce an audit/lineage row carrying user_id + org_id; enterprise profile
  with no token raises on the first turn.

### F2 — RBAC enforced by default under enterprise (verify + harden)
Likely MOSTLY DONE. Job = prove + close edges.
- Confirm `_rbac_mode()` returns "strict" when `CHUZOM_PROFILE=enterprise` and
  `CHUZOM_RBAC_MODE` unset; "off" under developer. Confirm enforcement raises
  `PermissionDenied` (ROUTE_PROMPT) BEFORE any provider call (zero spend on deny).
- Add a startup assertion in `verify_enterprise.py`: enterprise profile + RBAC
  resolving to "off" → loud warning (mis-set canary).
- Test (`test_f2_rbac_default_strict.py`): enterprise default = strict; a token
  lacking ROUTE_PROMPT is rejected pre-dispatch; explicit `CHUZOM_RBAC_MODE=warn`
  still allows (canary path); developer profile unaffected.

### F3 — Audit-row-per-turn from the router + chain integrity (verify + test)
Likely PARTIALLY done (`test_tier1_audit_per_turn.py` exists). Job = ensure the
router path writes through `AuditLog.append` under enterprise and prove the chain.
- Ensure each routed turn appends an `AuditEventType.ROUTING_DECISION` row with
  actor_id/org_id/model/cost; ensure `CHUZOM_AUDIT_DISABLED` is refused under
  enterprise (G-003 — verify still true).
- Test (`test_f3_audit_chain_integrity.py`): N routed turns → N appended rows;
  `verify_chain()` passes clean and reports the first divergent row after an
  out-of-band UPDATE; `CHUZOM_AUDIT_DISABLED=1` under enterprise does NOT silence
  audit.

### F4 — Per-identity quota enforced on the routing path
Goal: the per-user/per-team quota (`enterprise/quotas.py`) is CHECKED in
`route_and_call`, not just provider-level budget.
- Before dispatch (after identity + RBAC, before provider call), consult
  `QuotaTracker` for the resolved identity's daily/monthly cap; on breach raise a
  typed quota error (pre-emptive refusal, zero spend). On success, record
  consumption after the provider returns actual cost.
- Gate by enterprise profile (developer profile unchanged). Reuse the existing
  budget-lock pattern for atomicity if quotas share the spend path.
- Test (`test_f4_per_identity_quota.py`): a user at/over cap is refused before any
  provider call; under-cap proceeds and consumption is recorded; developer profile
  ignores per-identity quota.

### F5 — Complete the admin API stubs (G-006)
Implement the endpoints returning 501 today (confirm exact set in `admin_api.py`;
the audit named create-user, issue-token, query-audit, push-policy):
- POST create-user → `IdentityStore.create_user` (+ `get_or_create_org`/`team`).
- POST issue-token → `IdentityStore.issue_token` (return plaintext ONCE).
- GET query-audit → `AuditLog` read/export (CEF/JSON/CSV), permission-gated
  (VIEW_ALL_AUDIT / EXPORT_AUDIT).
- POST push-policy → validate + persist + emit an audit row (leave G-007
  versioning/rollback as a TODO; don't balloon F5 into it).
- All behind the existing admin bearer auth + RBAC permission checks.
- Test (`test_f5_admin_api_endpoints.py`): see §3 below.

### Cross-cutting
- No silent `except Exception` on enforcement paths — a failed RBAC/quota/audit
  check under enterprise must fail loud.
- Annotate enforced points:
  `# 🥷 Backslash-security: Enforce auth/authz to prevent unauthorized access.`
- Keep developer-profile behavior byte-for-byte unchanged (regression-guard).

### Acceptance (run before reporting done)
- `uv run pytest tests/test_f1_*.py tests/test_f2_*.py tests/test_f3_*.py tests/test_f4_*.py tests/test_f5_*.py -q` → green
- `uv run pytest tests/test_tier1_identity.py tests/test_tier1_audit_per_turn.py tests/test_t1_m2_rbac_route_prompt.py tests/test_enterprise_identity_required.py tests/test_admin_api_skeleton.py -q` → green (no regression)
- `uvx ruff check src/ tests/` → clean
- Manual: `CHUZOM_PROFILE=enterprise` + a ROUTE_PROMPT-lacking token → routed turn
  refused pre-dispatch, audit row written, zero provider spend.

### Sequencing (each step independently testable; commit per step)
0 assess → F1 (identity attribution) → F3 (audit per turn) → F2 (RBAC default,
verify) → F4 (quota wiring) → F5 (admin API). F1+F3 first so F2/F4 enforcement is
audit-visible; F5 last (additive, lowest coupling). Two PRs: F1–F4 (routing-path
enforcement) and F5 (admin API).

---

## 3. F5 admin-API test fixtures (paste-ready)

The one real adaptation: align the **app factory + auth-dependency shape** to
`admin_api.py` (read it in Step 0). If `admin_api.py` binds a module-level `app`
to its own store, refactor it to `create_admin_app(store=None)` — exactly like
`scim_api.create_scim_app(store=...)` — so tests inject a tmp store. Centralized
path constants (`USERS`/`AUDIT`/`POLICY`) get fixed in one place once the real
prefixes are known (the audit referenced `/v1/admin/users/{id}/tokens`).

```python
# tests/test_f5_admin_api_endpoints.py
"""F5: admin API endpoints — happy path + 401 (no token) + 403 (insufficient perm).

Auth model assumed (align to admin_api.py in Step 0): admin endpoints take a
Bearer chuzom 'tsr_' token -> IdentityStore.authenticate() -> RBAC permission
check. An ADMIN token passes; an EMPLOYEE token is 403 on privileged routes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("httpx")  # FastAPI TestClient transport
from fastapi.testclient import TestClient  # noqa: E402

from chuzom.enterprise.identity import IdentityStore  # noqa: E402
from chuzom.enterprise.rbac import Permission, Role  # noqa: E402


@pytest.fixture
def seeded(tmp_path: Path):
    # check_same_thread=False: TestClient dispatches handlers on a worker thread.
    store = IdentityStore(db_path=tmp_path / "identity.db", check_same_thread=False)
    org = store.create_org("acme")
    team = store.create_team(org.id, "default")

    admin = store.create_user(org_id=org.id, team_id=team.id,
                              email="admin@acme.com", display_name="Admin",
                              role=Role.ADMIN)
    employee = store.create_user(org_id=org.id, team_id=team.id,
                                 email="emp@acme.com", display_name="Emp",
                                 role=Role.EMPLOYEE)
    admin_tok = store.issue_token(admin.id, name="admin-cli").plaintext
    emp_tok = store.issue_token(employee.id, name="emp-cli").plaintext

    yield {
        "store": store, "org": org, "team": team,
        "admin": admin, "employee": employee,
        "admin_tok": admin_tok, "emp_tok": emp_tok,
    }
    store.close()


@pytest.fixture
def client(seeded):
    # ADAPT IN STEP 0: import the real admin app factory from admin_api.py and
    # inject the seeded store, e.g.:
    #   from chuzom.admin_api import create_admin_app
    #   app = create_admin_app(store=seeded["store"])
    from chuzom.admin_api import create_admin_app

    app = create_admin_app(store=seeded["store"])
    with TestClient(app) as c:
        yield c


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# Adapt these to the real router prefixes in admin_api.py (fix in one place).
USERS = "/v1/admin/users"
AUDIT = "/v1/admin/audit"
POLICY = "/v1/admin/policy"


@pytest.mark.parametrize("method,path", [
    ("post", USERS),
    ("get", AUDIT),
    ("post", POLICY),
])
def test_requires_auth(client, method, path):
    assert getattr(client, method)(path, json={}).status_code == 401


def test_rejects_unknown_token(client):
    assert client.get(AUDIT, headers=_bearer("tsr_not_real")).status_code == 401


def test_employee_cannot_create_user(client, seeded):
    r = client.post(USERS, headers=_bearer(seeded["emp_tok"]),
                    json={"email": "x@acme.com", "display_name": "X", "role": "employee"})
    assert r.status_code == 403


def test_employee_cannot_query_audit(client, seeded):
    assert client.get(AUDIT, headers=_bearer(seeded["emp_tok"])).status_code == 403


def test_employee_cannot_push_policy(client, seeded):
    r = client.post(POLICY, headers=_bearer(seeded["emp_tok"]), json={"name": "p"})
    assert r.status_code == 403


def test_admin_creates_user(client, seeded):
    r = client.post(USERS, headers=_bearer(seeded["admin_tok"]),
                    json={"email": "new@acme.com", "display_name": "New", "role": "employee"})
    assert r.status_code in (200, 201)
    assert r.json()["email"] == "new@acme.com"
    assert seeded["store"].get_user_by_email("new@acme.com").role == Role.EMPLOYEE


def test_admin_issues_token_plaintext_once(client, seeded):
    created = client.post(USERS, headers=_bearer(seeded["admin_tok"]),
                          json={"email": "svc@acme.com", "display_name": "Svc",
                                "role": "service_account"}).json()
    user_id = created["id"]
    r = client.post(f"{USERS}/{user_id}/tokens", headers=_bearer(seeded["admin_tok"]),
                    json={"name": "ci"})
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["token"].startswith("tsr_")
    ident = seeded["store"].authenticate(body["token"])
    assert Permission.ROUTE_PROMPT in ident.permissions
    again = client.get(f"{USERS}/{user_id}/tokens", headers=_bearer(seeded["admin_tok"]))
    if again.status_code == 200:
        assert "tsr_" not in again.text  # plaintext never returned again


def test_admin_queries_audit(client, seeded):
    r = client.get(AUDIT, headers=_bearer(seeded["admin_tok"]))
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict))


def test_admin_pushes_policy_writes_audit(client, seeded):
    r = client.post(POLICY, headers=_bearer(seeded["admin_tok"]),
                    json={"name": "prod-routing", "default_chain": "code_chain"})
    assert r.status_code in (200, 201)
    assert client.get(AUDIT, headers=_bearer(seeded["admin_tok"])).status_code == 200
```

Why these assertions are correct by construction (verified against the tree):
- `EMPLOYEE` lacks `MANAGE_USERS` / `VIEW_ALL_AUDIT` / `MANAGE_POLICY` and `ADMIN`
  has all twelve permissions (`src/chuzom/enterprise/rbac.py`), so the 403/200
  split holds.
- `issue_token` returns `plaintext` exactly once (`APIToken.plaintext`,
  `src/chuzom/enterprise/identity.py`), so the "plaintext once" check matches the
  store's real contract.
- `check_same_thread=False` is required because `TestClient` dispatches on a
  worker thread (same reason `scim_api` tests use it).
