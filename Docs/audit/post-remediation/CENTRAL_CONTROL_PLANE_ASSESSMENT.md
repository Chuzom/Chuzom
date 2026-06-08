# Central Control-Plane Assessment

**Question being answered.** Can a central platform team govern all model usage from one place?

**Verdict:** **Not ready.** What exists today is shared configuration and a per-process audit log, not a control plane. Calling it "configuration layer only" is the most charitable framing.

---

## 1. Administrative capability matrix

Legend:
- **UI** — graphical admin interface
- **API** — programmatic admin endpoint
- **Cfg** — configuration-file or env-variable support
- **Enf** — actually enforced at runtime, not just configured
- **Aud** — administrative action audited

| Capability | UI | API | Cfg | Enf | Aud | Evidence |
|---|---|---|---|---|---|---|
| Define organisation | ❌ | ❌ | ⚠️ | ❌ | ❌ | `enterprise/identity.py:35` defines `Org` dataclass; no admin API. `IdentityStore` is SQLite-direct. |
| Define team | ❌ | ❌ | ⚠️ | ❌ | ❌ | `enterprise/identity.py:44` defines `Team`. Same gap. |
| Define user | ❌ | ❌ | ⚠️ | ❌ | ❌ | `User` + `APIToken` schemas exist (`identity.py:55,70`). Token issuance / revocation not exposed. |
| Define service account | ❌ | ❌ | ⚠️ | ❌ | ❌ | No service-account abstraction; `CHUZOM_USER_ID` env is the only identity primitive consumed by routing. |
| Define developer tool / agent | ❌ | ❌ | ❌ | ❌ | ❌ | No first-class tool/agent registry that the control plane references. |
| Provider account | ❌ | ❌ | ✅ | ✅ | ❌ | Provider keys in env / `.env`. Enforced (no key = provider unreachable). |
| Model alias | ❌ | ❌ | ✅ | ✅ | ❌ | `config/models.yaml`, `profiles.py` enforce chain order. |
| Policy | ❌ | ❌ | ⚠️ | ⚠️ | ❌ | `policy.py` carries allow/deny shape. No team scope. |
| Budget | ❌ | ❌ | ✅ | ⚠️ | ❌ | `config.chuzom_monthly_budget` global only (INV-011). Per-team / per-user / per-agent: absent. |
| Quota | ❌ | ❌ | ⚠️ | ❌ | ❌ | `enterprise/quotas.py::QuotaTracker` exists but not imported by router (`grep "QuotaTracker" src/chuzom/router.py` empty). |
| Region | ❌ | ❌ | ❌ | ❌ | ❌ | No region abstraction. |
| Environment (dev / stage / prod) | ❌ | ❌ | ⚠️ | ❌ | ❌ | No env scoping for policies. |
| Data classification | ❌ | ❌ | ❌ | ❌ | ❌ | No data classifier; redaction module unwired (PRI-001). |
| Emergency restriction | ❌ | ❌ | ❌ | ❌ | ❌ | No emergency kill switch; config edits require restart. |

**Result.** No row has all five columns green. **There is no control plane.** What exists is a set of YAML / env / SQLite primitives that an operator could in principle assemble into one, with significant engineering work.

---

## 2. Configuration rollout

| Question | State |
|---|---|
| Define organisation-wide defaults | Per-instance only. |
| Override defaults by team / project | Not modelled. |
| Apply policies by user / tool / repo / env / agent | Not modelled. |
| Roll out configuration safely | Manual file copy / env var change per host. |
| Preview policy effects | Not supported. |
| Version policies | Not supported. |
| Approve / roll back | Not supported. |
| Audit policy changes | Not supported. |
| Stage by environment | Not supported. |

---

## 3. Emergency controls

| Action | Supported? | Notes |
|---|---|---|
| Disable a provider immediately | ⚠️ Partial | Removing the env var prevents new calls **on instances that restart**. Running processes need restart. No control-plane signal. |
| Disable a model immediately | Same as above. |
| Block a compromised credential | ❌ | No control-plane revocation. Credential rotation is per-host. |
| Enforce data-residency restrictions | ❌ | No region abstraction. |
| Restrict sensitive workloads to approved providers | ❌ | No data-classifier; no per-classification routing. |
| Set emergency global spending caps | ⚠️ | `chuzom_monthly_budget` is global; a hard cap can be set, but is not coordinated across instances. |
| Pause an agent or workflow | ❌ | No control-plane action on agent identity. |

---

## 4. Inspect / export

| Capability | State |
|---|---|
| Inspect routing decisions centrally | ❌ | `tools/dashboard.py` is per-host. |
| Export usage and cost data | ⚠️ | Per-host SQLite (`~/.chuzom/usage.db`, `~/.chuzom/audit.db`). Aggregating across the fleet is the operator's problem. |
| SIEM integration | ⚠️ | `enterprise/audit.py` has CEF/JSON/CSV exporters. No daemon or scheduled-pipeline integration; the operator must script the pull. |
| Enterprise identity | ❌ | No SSO/SAML/OIDC/SCIM. |

---

## 5. Distributed consistency

| Question | Evidence |
|---|---|
| Do two chuzom instances enforce the same policy? | Only if they share the same `.env` and `~/.chuzom/profile.yaml`. No reconciliation between them. |
| Do two instances share budget state? | No. `_pending_spend` (`router.py`) is per-process. The persistent `usage.db` is per-user-per-host. |
| Do two instances share circuit-breaker state? | No. `HealthTracker` is an in-process singleton (`health.py:259`). |
| Do two instances share audit chain? | If they write to the same `audit.db` (same OS user, same host), SQLite file-locking serialises. Across hosts: no. |

---

## 6. What it would take to make this real

The 10 must-haves for a credible central control plane in chuzom:

1. **Control-plane service**. A single source of truth for orgs / teams / users / agents / policies / budgets, with its own audit log (separate from the routing audit log).
2. **Policy as a versioned, scoped, approvable object** — not a YAML file.
3. **Push or pull?** Decide: do chuzom instances long-poll the control plane (pull) or receive control-plane events (push)? Each has trade-offs.
4. **SSO / SCIM / OIDC integration**. Drop `CHUZOM_USER_ID`-as-trust; principals come from the IdP.
5. **Token-issuance pipeline** + revocation, expiry, scope.
6. **Per-team / per-project budgets** persisted in a central store; checked atomically per call.
7. **Cross-instance audit reconciliation**. Either (a) single-writer log per tenant, (b) per-instance log + reconciliation job, or (c) stream all events to a central sink. Pick one.
8. **Provider-key brokerage**. Credentials live in a vault; chuzom instances fetch ephemeral tokens. No more keys in dev `.env`.
9. **Admin API + UI** for the daily operations (rotate, retire, freeze, export).
10. **Documented operator runbook**, covering every cell that has UI = ❌ today.

None of the ten exist in code on `main` as of audit time.

---

## 7. Verdict

The capability table has many ⚠️ rows. The temptation to read those as "almost ready" should be resisted. **A control plane with no enforced rows is not a control plane.** Per the assignment of capability statuses: every capability that has UI, API, Cfg without Enf must be counted as **not complete**. Under that rule, **zero rows are complete**.

The remediation cycle did not change the control-plane picture. It tightened the routing chokepoint (identity + audit per turn) — a necessary precondition — but did not build a central plane on top of it.

**Recommendation:** publish the 10-item must-have list as the v0.3.x / v0.4.x agenda. Do not market chuzom as having central governance until the Enf column has its first ✅.
