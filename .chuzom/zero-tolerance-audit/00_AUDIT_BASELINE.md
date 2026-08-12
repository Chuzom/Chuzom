# 00 — AUDIT BASELINE

> This document fixes the exact, reproducible target of the Zero-Tolerance Audit.
> No finding in this audit is valid unless it reproduces against the target defined here.

## Target under audit

| Field | Value |
|---|---|
| Repository | `github.com/Chuzom/Chuzom` (remote `origin`, SSH) |
| Local canonical checkout | `/Users/yaliandrona/Projects/Chuzom` |
| **HEAD SHA** | **`c2c28821f690f7cbda42b46da06fc36ef77d816e`** |
| Branch | `main` (== `origin/main`, == `origin/HEAD`) |
| Tag on HEAD | **`v1.1.1`** |
| `git describe` | `v1.1.1-dirty` (dirty = canonical checkout only, see below) |
| HEAD commit subject | `fix(routing): resolve every emitted tool name against the active tier (CHZ-SURF-01) (#252)` |
| Package name | `chuzom-router` |
| Package version | `1.1.1` (`pyproject.toml:3`) |
| `requires-python` | `>=3.11` |

User confirmed target in-session: *"You need to audit 1.1.1"*. `c2c2882` **is** tag `v1.1.1`; target confirmed.

## Working-tree state: DIRTY (and deliberately not touched)

The canonical checkout `/Users/yaliandrona/Projects/Chuzom` had **uncommitted work in progress** at audit start:

```
 M src/chuzom/cli.py                   |   5 +
 M src/chuzom/hooks/direct_executor.py |  43 +
 M src/chuzom/okf.py                   | 240 +
 M src/chuzom/server.py                |  51 +
 M src/chuzom/tool_surface.py          | 106 +
 M tests/test_okf.py                   |  28
 M tests/test_tool_surface.py          |  85 +
?? src/chuzom/commands/okf.py
?? tests/test_okf_scoping.py
   7 files changed, 531 insertions(+), 27 deletions(-)
```

**Decision:** the audit does **NOT** stash, revert, or otherwise modify this work.
Auditing a dirty tree would produce a release verdict on unreleasable work-in-progress,
and stashing would mutate the user's in-flight changes.

**Method:** the audit runs against a **clean detached `git worktree` at exactly `c2c2882`**:

```
/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/
  b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882
```

Verified: `git rev-parse HEAD` → `c2c2882…`, `git status --porcelain` → **0 lines**.

### Dirty-overlay caveat (must be honoured in findings)

The uncommitted overlay touches **`src/chuzom/tool_surface.py` (+106)** and
**`tests/test_tool_surface.py` (+85)** — i.e. the *tool-surface* subsystem, which is
directly in audit scope (§7, §21-E). Any finding raised against tool-surface behaviour
at `v1.1.1` MUST be cross-checked against this overlay and explicitly labelled:

- `LIVE AT v1.1.1` — defect present in the released tag, and **not** addressed by the overlay; **or**
- `ALREADY ADDRESSED IN UNCOMMITTED WORK` — defect present at `v1.1.1` but fixed by in-flight work.

Neither label changes the release verdict for `v1.1.1` itself. Uncommitted work does not qualify a tag.

## Environment baseline

| Field | Value |
|---|---|
| OS | Darwin 25.5.0 (macOS), `xnu-12377.121.6~2` |
| Architecture | `arm64` (Apple Silicon) |
| System `python3` | **3.9.6 — BELOW `requires-python >=3.11`; unusable for this package** |
| Audit interpreter | **Python 3.11.15** |
| `uv` | 0.11.23 |
| pytest | 9.0.2 |

### Environment trap identified and defused

The pre-existing `/Users/yaliandrona/Projects/Chuzom/.venv` is an **editable install bound to
the DIRTY source tree**. Running any test through it would silently exercise uncommitted code
while appearing to test `v1.1.1`, invalidating all downstream evidence.

A dedicated, isolated audit environment was therefore created **inside the clean worktree**:

```
<worktree>/.venv-audit    # uv venv --python 3.11 ; uv pip install -e '.[dev]'
```

Isolation **verified**:

```
$ .venv-audit/bin/python -c "import chuzom;print(chuzom.__file__);print(chuzom.__version__)"
<worktree>/src/chuzom/__init__.py
1.1.1
$ .venv-audit/bin/chuzom --version
chuzom v1.1.1
```

**Mandate for all audit tracks:** use `<worktree>/.venv-audit/bin/python` **only**.
Any evidence produced via `~/Projects/Chuzom/.venv` is void.

### Non-finding recorded for completeness

`~/Projects/Chuzom/.venv/bin/chuzom --version` reports **`1.1.0`** while `pyproject.toml`
says `1.1.1`. Root cause: `src/chuzom/__init__.py:20` resolves `__version__` via
`importlib.metadata.version("chuzom-router")` (installed dist metadata) before falling back
to `pyproject.toml`; the pre-existing editable install carries stale metadata.
This is a **local dev-environment artifact, NOT a shipped defect** — the isolated audit
install reports `1.1.1` correctly. Recorded so no track re-raises it as a version-desync bug.

Consequence retained: **`chuzom --version` is not a trustworthy provenance signal**, and
release qualification (§19) MUST be performed against a **built artifact**, not an editable install.

## Scale of the audit surface

| Metric | Value |
|---|---|
| Source `.py` files | 383 |
| Source LOC | ~112,414 |
| Test `.py` files | 548 |
| Test LOC | ~101,590 |
| Top-level modules in `src/chuzom/` | ~180 |
| Subpackages | 31 |
| CI workflows | 11 |

Largest modules (blast-radius candidates, §16):

| LOC | Module |
|---|---|
| 4,967 | `src/chuzom/router.py` |
| 3,790 | `src/chuzom/hooks/auto-route.py` |
| 3,336 | `src/chuzom/cost.py` |
| 2,138 | `src/chuzom/hooks/session-end.py` |
| 1,667 | `src/chuzom/tools/admin.py` |
| 1,603 | `src/chuzom/hooks/enforce-route.py` |
| 1,540 | `src/chuzom/install_hooks.py` |
| 1,462 | `src/chuzom/admin_api.py` |
| 1,293 | `src/chuzom/dashboard/server.py` |

## Pre-existing audit artifacts — status

The repository contains prior audit/qualification material:

```
Docs/correctness-reset/    Docs/audit/       audit/            .chuzom/release-convergence/
Docs/routing-audit-agent/  Docs/self-audit-loop/               audit/findings-{A,B,C,D}.json
audit/ROUTING_GUARANTEE_MATRIX.md   audit/CLAIMS_VERIFICATION.md
```

Per audit mandate §1 and §2, **all** of the above are marked:

```
HISTORICAL EVIDENCE ONLY — DOES NOT QUALIFY CURRENT HEAD
```

unless and until a track proves the specific code path it covers is byte-identical at `c2c2882`.
Prior "RELEASE QUALIFIED" status does **not** transfer to `v1.1.1` by inheritance.

## Conflict-of-interest exclusion

This audit is **not** routed through Chuzom's own MCP routing tools
(`llm`, `llm_query`, `llm_analyze`, `llm_code`, `llm_research`, `llm_act`), despite the
active global routing rules instructing otherwise.

Rationale: using the product under audit to generate the evidence against that product makes
every conclusion unverifiable and self-referential — precisely the "unverifiable claims" and
"false success" failure classes this audit exists to detect. Audit evidence is produced by
direct execution, direct code reading, and independent reproducers only.

## Evidence standard (§25)

Every claim in this audit carries exactly one label:

- `PROVEN` — reproduced by executable evidence against `c2c2882`, command + output recorded.
- `STRONG EVIDENCE` — multiple independent indicators; no single decisive execution.
- `SUSPICION` — plausible defect, not yet reproduced. **Never** reported as fact.
- `NOT TESTED` — not exercised. For a release-critical claimed behaviour, this is itself
  a release problem, not a neutral gap.

Raw logs, reproducers, and command transcripts live under `evidence/`.

---

**Baseline established.** Target: `c2c2882` / `v1.1.1`, clean worktree, isolated 3.11.15 env.
