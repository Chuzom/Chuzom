# 35 · Release pipeline — agent graph, sequencing, and gates

**Written 2026-08-18.** Doc 34 named four launch steps and recorded three decisions. Two of
those decisions created work: **finish the mcp 2.0 port** (Step 3) and **complete the install
verification** (Step 1). This document is the execution plan for both, plus the publish that
follows — as an agent graph, with what each stage must prove before the next begins.

## The one property that shapes everything below

**Publishing to PyPI is irreversible.** A version number cannot be reused. Everything else in
this audit had a control: break it, observe the failure, fix it, re-run. A release has none —
the only test is the one you run *before*.

So the graph is not "do the work, then publish". It is **two independent verification tracks
that must both go green, joined by a gate that can refuse**, and a publish stage that runs
against TestPyPI first for a reason that is not ceremony: it is the only rehearsal available.

---

## 1 · Shape

```
                 ┌──────────────────────────────────────┐
                 │  A · mcp-2.0 port      (sequential)  │
   inventory ───▶│  A1 rename → A2 verify → A3 downstream│──┐
       │         └──────────────────────────────────────┘  │
       │                                                    ├──▶ release-gate ──▶ publish
       │         ┌──────────────────────────────────────┐  │      (verifier,        │
       └────────▶│  B · install proof     (parallel)     │──┘       can refuse)      ▼
                 │  B1 container  B2 timing  B3 matrix   │                      post-verify
                 │       └──── parallel ────┘            │
                 └──────────────────────────────────────┘
```

**A and B are independent** — the port touches `src/`, the install proof touches packaging and
CI. Running them in sequence would double the wall-clock for no coupling. **B1/B2/B3 are
independent of each other** and fan out.

**A is strictly sequential.** A2 cannot verify a port that A1 has not finished, and A3
(downstream re-verification) is meaningless until A2 proves the upstream port is correct.

---

## 2 · The graph

```yaml
apiVersion: agr/v1.7
name: chuzom-release
description: Finish the mcp 2.0 port and prove the install path, then publish — gated.
category: software-engineering

nodes:
  - id: inventory
    speciality: analyst
    abilities: [analyze]
    inputs: [repo]
    outputs: [port_surface, doc_commands, risk_map]

  # ── Track A · the port. Sequential: each stage needs the previous one's output.
  - id: port-rename
    speciality: engineer
    abilities: [edit, run_suite]
    inputs: [port_surface]
    outputs: [renamed_modules, tests_failing: int]

  - id: port-verify
    speciality: qa-lead
    kind: verifier
    abilities: [run_suite]
    inputs: [renamed_modules]
    outputs: [suite_green: any, resolves_from_wheel: any]

  - id: port-downstream
    speciality: engineer
    abilities: [edit, run_suite]
    inputs: [suite_green]
    outputs: [downstream_verified: any]

  # ── Track B · the install proof. B1/B2/B3 fan out — none depends on another.
  - id: install-container
    speciality: qa-lead
    kind: verifier
    abilities: [run_command]
    inputs: [doc_commands]
    outputs: [clean_install_ok: any, mcp_connects: any]

  - id: install-timing
    speciality: qa-lead
    abilities: [run_command]
    inputs: [doc_commands]
    outputs: [seconds_measured: int]

  - id: install-matrix
    speciality: qa-lead
    kind: verifier
    abilities: [run_suite]
    inputs: [doc_commands]
    outputs: [platforms_green: int, pythons_green: int]

  # ── The gate. Joins BOTH tracks and may refuse.
  - id: release-gate
    speciality: tech-lead
    kind: verifier
    abilities: [read_diff]
    join: all
    inputs: [downstream_verified, clean_install_ok, seconds_measured, platforms_green]
    outputs: [cleared_to_publish: any, blocking_reason]

  - id: publish
    speciality: release-manager
    abilities: [run_command]
    inputs: [cleared_to_publish]
    outputs: [testpypi_ok: any, pypi_url]

  - id: post-verify
    speciality: qa-lead
    kind: verifier
    abilities: [run_command]
    inputs: [pypi_url]
    outputs: [installs_from_index: any]

edges:
  - {from: inventory, to: port-rename}
  - {from: inventory, to: install-container}
  - {from: inventory, to: install-timing}
  - {from: inventory, to: install-matrix}
  - {from: port-rename, to: port-verify}
  - {from: port-verify, to: port-rename, when: not suite_green and attempts < 3}
  - {from: port-verify, to: port-downstream, when: suite_green}
  - {from: port-downstream, to: release-gate}
  - {from: install-container, to: release-gate}
  - {from: install-timing, to: release-gate}
  - {from: install-matrix, to: release-gate}
  - {from: release-gate, to: publish, when: cleared_to_publish}
  - {from: publish, to: post-verify}

termination:
  max_steps: 80
  contract: >
    published to PyPI only after both tracks proved green, and the published
    artifact re-installs from the index into a clean environment

verification:
  - describe: the port is complete on the target major
    assert: output.suite_green == true and output.resolves_from_wheel == true
  - describe: every documented command works in a clean container
    assert: output.clean_install_ok == true and output.mcp_connects == true
  - describe: the matrix covered three platforms and both Python bounds
    assert: output.platforms_green == 3 and output.pythons_green == 2
  - describe: the release was gated, not merely reached
    assert: output.cleared_to_publish == true
  - describe: the published artifact actually installs
    assert: output.installs_from_index == true
```

`framework-migration` (agenticgraphs) is the closest existing shape and its
`port-slice → integrate → supervise` retry loop is reused above as
`port-rename → port-verify → port-rename`. It is not used directly: it has no second track
and no refusable gate, and both matter here.

---

## 3 · Acceptance criteria

Every criterion is a command with an expected exit code or a number with a threshold — the
constraint from doc 34, for the reason given there.

### A1 · `port-rename`

- [ ] `grep -rn "inputSchema\|serverInfo\|protocolVersion" src/ tests/` returns **0** in code
      (comments explaining the rename are fine, and the check must distinguish them — a plain
      string search will trip on its own explanation, which happened twice today).
- [ ] `tests_failing == 0` where it was **17**.
- [ ] `pyproject` pin and `_SUPPORTED_MAJOR` move in the **same commit** as the imports.

### A2 · `port-verify` *(verifier — blocks A3)*

- [ ] `uv run --with "mcp>=2.0.0,<3.0.0" python -c "import chuzom.server"` → **exit 0**.
- [ ] Full suite green against real 2.0.0: **7436+ passed, 0 failed**.
- [ ] `CHUZOM_REQUIRE_WHEEL=1` run resolves from **site-packages**, not `src/` — G-D's own
      precondition, and the thing that made an earlier "verified" claim hollow.

### A3 · `port-verify-discriminating`

> **CORRECTED 2026-08-18.** This stage originally read *"llm-router re-verified against the
> renamed fields"* — work in the downstream repository, which contradicts the standing
> direction that everything lands upstream first and downstream receives copies at sync time.
> I followed this plan instead of that instruction and had to revert the result
> (llm-router `c97c3ee`). **A plan that contradicts a standing direction is a defect in the
> plan, not authority to ignore the direction** — corrected here so the next reader is not
> sent down the same path.

- [ ] A test asserting the renamed fields **directly**, upstream. The handshake tests read
      them incidentally while checking something else, so a major-version mismatch surfaces
      as a missing attribute inside a server fixture rather than as a statement about the
      version.
- [ ] It must **discriminate**: pass on 2.x and **fail on 1.x**. "The suite passes" is what
      made the downstream claim hollow — that suite passed regardless of which major was
      installed, so it was never evidence about the port.
- [ ] Doc 33's L1 status moves to VERIFIED **only if** the control holds.
- [ ] Downstream receives this as a **copy at sync time**, not as separate work.

### B1 · `install-container` *(verifier — blocks the gate)*

- [ ] `pip install chuzom-router` in a **container with no repo checkout** → exit 0.
- [ ] `claude mcp list` reports **connected**, not `CONNECTION_CLOSED`.
- [ ] **Zero** manual steps not in the README.

### B2 · `install-timing`

- [ ] Wall-clock measured. Either **≤60s** or the README states the real number. An
      unmeasured claim fails; a slower honest one passes.

### B3 · `install-matrix` *(verifier — blocks the gate)*

- [ ] ubuntu **and** macos **and** windows → `platforms_green == 3`.
- [ ] Python 3.11 **and** 3.14 → `pythons_green == 2`.
- [ ] Windows is not optional. The audit's Windows failure was invisible on every locally
      reachable platform, and its cause lived in a shell-quoted command of exactly the kind
      this stage runs.

### GATE · `release-gate` *(must be able to refuse)*

- [ ] **All four** upstream outputs present and true. `join: all` — a missing track is a
      refusal, not a pass.
- [ ] PR #253 at **34/34**.
- [ ] `git status --porcelain` **empty**; the release commit is pushed.
- [ ] Version in `pyproject` **not already on PyPI** — checked against the live index, since
      this is the one mistake that cannot be undone.
- [ ] On refusal, `blocking_reason` names the failing criterion. "Not ready" is not a reason.

### PUBLISH · `publish`

- [ ] **TestPyPI first.** `twine upload --repository testpypi` → exit 0, then
      `pip install -i https://test.pypi.org/simple/ chuzom-router` in a clean container → exit 0.
      This is the only rehearsal an irreversible action gets.
- [ ] Only then the real upload.
- [ ] A git tag matching the published version.

### POST · `post-verify` *(verifier)*

- [ ] `pip install chuzom-router==<version>` from the **real index**, clean container → exit 0.
- [ ] `chuzom --version` prints the published version.
- [ ] `claude mcp list` connected.
- [ ] If this fails, **yank** — a broken release left up is worse than a yanked one.

---

## 4 · Parallelism, and what it is not for

A and B run concurrently because they are independent, not to be fast. **Nothing downstream of
the gate is parallel**, and the gate joins on `all`. Speed before an irreversible action is a
poor trade: the wall-clock saved is minutes, and the cost of a bad release is a version number
that can never be reused.

B1/B2/B3 fan out for the same reason and with the same limit — all three report into the gate,
and any one of them failing refuses the release.

## 5 · Where this can still go wrong

Stated because a plan that lists only its successes is the shape of every over-claim this audit
found:

- **B1 is the weakest stage.** A container "clean enough" is a judgement, and this session
  already produced a `HOME=/tmp/empty` probe that was neither the developer's environment nor
  CI's, and produced 38 failures belonging to neither. If B1's container inherits credentials,
  a cache, or a `~/.chuzom`, it proves less than it claims.
- **A3 cannot be satisfied by a passing suite.** llm-router's suite already passes and already
  missed these fields. A test that touches them must be added first, or A3 is theatre.
- **The gate is only as good as its inputs.** Four booleans from four agents. If a verifier
  reports green on a check that could not fail — the defect in every entry of doc 33's opening
  table — the gate passes a release that should have been refused.
