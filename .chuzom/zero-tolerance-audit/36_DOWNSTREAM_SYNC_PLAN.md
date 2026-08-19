# 36 · Downstream sync — advancing llm-routing to the upstream core

**Written 2026-08-19.** Upstream shipped `1.3.0` to PyPI. This document is how the downstream
package (`llm-routing`, published at **12.0.0**, 49 releases) gets the same core, under its own
brand, and what has to be true before each step.

Read docs 33–35 first if you have not: 33 is the open-work list, 34 the launch criteria, 35 the
release pipeline and its gates. This one is narrower — it covers the sync only.

---

## 0 · Facts to start from, verified

| | |
|---|---|
| downstream package name | **`llm-routing`** — *not* `llm-router`, which is an unrelated package at 0.1.1 |
| downstream published | **12.0.0** |
| downstream `main` | `72dd582` — contains **none** of the 2026-08-18 fixes |
| downstream open PR | **#38** — the mcp 2.0 fix, 2763 passing, unmerged |
| upstream published | **1.3.0** |
| size delta | upstream 392 files / 117k lines; downstream 203 / 64k |
| identifier rewrites | ~4,500 `chuzom` occurrences in upstream `src/` |

**A correction worth carrying:** the "downstream is at 0.1.1 while the repo says 12.0.0" alarm
raised on 2026-08-18 was wrong — it came from querying `llm-router` instead of `llm-routing`.
There is no version discrepancy. Recorded because the wrong version of that claim would have
blocked a release for no reason.

---

## 1 · Decisions already taken

Both by the maintainer, both binding on what follows:

**Scope — core routing only.** Copy the router, hooks, cost/savings, and the security fixes.
**Exclude** the wallet/marketplace tools, enterprise-only modules, and the audit tree. Measured
dependency cost of excluding them:

```
agoragentic            imported by 1 module
tenant_policy_sidecar  imported by 0
admin_api              imported by 2
invoice_reconciliation imported by 2
```

Five import sites to sever, not a rewrite. Exclusion is cheap here; that will not stay true if
the sync is deferred much longer.

**Env vars — rename to `LLM_ROUTER_*`, no fallback.** A clean break, documented in the release
note. Anyone with an old variable set loses that setting until they read the changelog. This is
the single largest breaking change in the sync and the main reason the version bump is major.

---

## 2 · Order of work

### Step 1 · Merge PR #38 — *do this first, before any sync*

It fixes a **total install breakage**: `mcp>=1.0.0` unbounded, `mcp 2.0.0` removed
`mcp.server.fastmcp`, so every fresh install of 12.0.0 dies at import and reports
`CONNECTION_CLOSED` — indistinguishable from a network fault.

Doing this before the sync keeps a small, reviewable, already-verified change separate from a
4,500-identifier rewrite. Merging it *into* the sync would bury a user-facing fix inside a diff
nobody can read.

- [ ] #38 merged, CI green
- [ ] Issues **#37, #35, #34** close on merge
- [ ] Consider shipping this alone as **12.0.1** — the install fix reaches users without waiting
      for the sync. Every day it waits is another day of broken fresh installs.

### Step 1.5 · Make upstream an actual superset — **added 2026-08-19, was not in the original plan**

Step 2 below says "copy upstream `src/` … into the downstream package layout". That is safe
only if upstream contains everything downstream does. **It does not**, and nobody had
checked — the plan asserted a containment relationship instead of measuring one.

`scripts/check_downstream_superset.py` measures it. Result on the day it was written:

```
upstream symbols:   2413
downstream symbols: 1340
downstream-only:    42  (21 public, 21 private)
path collisions:    2
```

The 21 public symbols are whole features, not stragglers:

| downstream file | absent upstream |
|---|---|
| `response_validation.py` | the entire module — `validate_response`, `validate_streaming_chunk`, `safe_extract_content`, … |
| `audit_routing.py` | `run_audit`, `score_decision`, `sample_unaudited_decisions`, `AuditedDecision` |
| `dashboard_data.py` | `query_realized_savings`, `RealizedSavingsTotals` |
| `signals/__init__.py` | `detect_pii`, `force_local_for_pii` |
| `cost.py` | `get_savings_by_task_type` |
| `commands/audit.py` | `cmd_audit` — the whole `audit` CLI command |
| `secret_scrubber.py` | `scrub_environment` |
| `capabilities.py` | `serialize_capability_decision` |
| `subscription_local_routing.py` | `set_pressure_provider` |
| `budget_envelope.py` | `budget_envelope_enabled` |

**The `audit_routing.py` collision is why this is a script and not a paragraph.** Both trees
have a file at that path and they are *unrelated features*: upstream is an append-only log of
routing turns (`audit_routing_turn`), downstream is a post-hoc misroute **scorer**
(`run_audit`, `score_decision`). A file copy overwrites one with the other — same path, no
merge conflict, no import error, no failing upstream test. The feature just stops existing.
That is the silent-deletion shape, and it is precisely what "copy `src/` across" produces
when the two trees are not the containment the instruction assumed.

- [ ] Port each downstream-only public symbol upstream, or record a decision not to
- [ ] `scripts/check_downstream_superset.py` exits 0
- [ ] Only then proceed to Step 2

This is also what the standing direction already required — *"after Chuzom is completely
ready, we'll copy its components"*. "Completely ready" cannot mean "missing 21 public symbols
the copy would delete." The direction was right; the plan under-specified what satisfying it
involved.

**Two upstream defects were already found this way**, before the script existed, from a
five-minute diff of one module:

- `QUOTA_BALANCED` and `SUBSCRIPTION_LOCAL` resolved to no chain at three of four lookup
  sites — `subscription_local` measured at **one** model (the paid seat, no fallback) under
  the profile whose purpose is preferring the free local bucket. Fixed in `8c38e38`.
- `subscription_local_routing` had **zero production callers** — module, enum member, gate,
  reorder and its own test file, all correct, all unreachable. Fixed in `de850da`.

Both were fixed downstream and never travelled back. The sync direction is not one-way, and
treating it as one-way is what let two live defects sit upstream.

### Step 2 · The sync

- [ ] Copy upstream `src/` minus the exclusion set, into the downstream package layout
- [ ] Rewrite identifiers: `chuzom` → `llm_router`, `CHUZOM_*` → `LLM_ROUTER_*`, paths, imports,
      docstrings
- [ ] `scripts/ci/check_identity.py` **passes** — that is the acceptance gate, and it exists
      precisely for this. It rejects upstream-name leakage; do not add allowlist entries to get
      it green.
- [ ] Full suite green on real `mcp>=2.0.0,<3.0.0`
- [ ] Version → **13.0.0**, synced across every manifest that carries it

### Step 3 · Close the remaining issues, with a released version

- [ ] **#36** — `DIRECT_EXECUTION` threat model. Upstream measured the blocklist at **3/12** and
      wrote the coverage table into SECURITY.md. Port that table, do not re-derive it.
- [ ] **#33** — Stop-hook verbosity. Upstream ships `full | condensed | disabled` with
      `condensed` as default; port the reasoning too, since the default change is the part a
      reader will question.
- [ ] Answer each issue **only once the fix is in a published version**. An issue closed against
      an unmerged branch tells the reporter their bug is fixed while the package still
      reproduces it.

---

## 3 · What must not be lost in translation

These are upstream fixes whose *reasoning* matters as much as their code. Porting the diff
without the comment reintroduces the defect one refactor later.

| fix | the thing that must survive the copy |
|---|---|
| path traversal (`code_context`) | prompt text is **not trusted input**; it carries pasted logs and tool output. Confinement reuses `is_safe_path` rather than reimplementing |
| ReDoS bound | measured, not assumed: realistic pasted text is 0.001s; only a crafted unbroken token blows up. Do not widen the claim |
| `private_opener` | the `chmod` stays **alongside** the opener — an opener only applies at creation and cannot repair files written by older versions |
| SEC-006 URL validation | **seven** readers bypassed it, found in three passes. The lint is what keeps the eighth from appearing |
| INV-COST-004 | savings surfaces **delegate**; three hand-rolled queries gave $73.97 / $102.31 / $205.19 for the same day |
| CHZ-WIN-01 | fix the **product**, not the CI env. Copying `PYTHONUTF8=1` into the job turns CI green while users still crash |

**SEC-002 layer 2 is still absent downstream** — `project_root` confinement, where
`_assert_under_root` / `FsSandboxError` have zero occurrences, and two `llm_fs_*` tools write.
Layer 1 (the gate) is in #38. Layer 2 is a breaking signature change and needs its own work.
There is a test that fails the day it lands, so it cannot be quietly forgotten.

---

## 4 · How to know the sync worked

Not "the tests pass" — that is what made the first mcp port look verified when it was not.

- [ ] `check_identity.py` clean, **without** new allowlist entries
- [ ] Full suite green against a real `mcp 2.0.0` install
- [ ] A test that **discriminates**: passes on 2.x and **fails on 1.x**. Upstream's
      `test_mcp2_field_names.py` fails all 7 cases on 1.x; the downstream suite passed 2726
      tests while missing the same renames entirely, because nothing referenced them
- [ ] Documented commands execute on **ubuntu, macos and windows**, py3.11 and 3.14 — the
      windows leg found a real product bug on its first run
- [ ] `pip install llm-routing==13.0.0` into a **clean container**, then `chuzom`-equivalent
      `--version` and `doctor` both work
- [ ] Post-verify from the **real index** after publishing. The workflow succeeding and the
      artifact installing are separate claims; on 2026-08-18 the index lagged and the first
      install attempt failed for a reason that looked identical to a broken release

---

## 5 · The habit that produced most of this week's findings

Written down because it transfers, and because the sync is exactly the kind of work where it
pays:

> **Is there already a helper for this, and does everything that needs it use it?**

Four genuine defects came out of 40 scanner alerts. Three had the same shape: a correct,
tested, documented mitigation already in the repository, and a parallel path that never used
it. The downstream gap is that shape one level up — a mitigation exists upstream and the
downstream repository never received it.

And the corollary, demonstrated three times: **writing the check finds more than reading the
code.** `lint_suite_env_parity` found the G-D gap; `lint_workflow_shell_portability` reproduced
the Windows failure exactly; `lint_ollama_url_readers` found four unvalidated readers and
refuted the document it was written to support. A check has to be right about every instance; a
reader only has to feel right about the ones they looked at.

Corollary to the corollary, learned the hard way on 2026-08-18: **new checks fail on their
first real run.** Of six CI failures on the sync PR, three were defects in guards written that
same day — an ambiguous variable name, a `skip` that made a guard silently partial, and a
resolver that only worked on a developer checkout. Budget for that; it is not a sign the checks
were a bad idea.
