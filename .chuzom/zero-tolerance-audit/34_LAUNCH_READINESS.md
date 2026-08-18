# 34 · Launch readiness — four steps, with criteria that can fail

**Written 2026-08-18.** Doc 33 bounded PR #253. This one is about a different question:
*what stands between the current state and a launch a new user can complete without help?*

The packaging is not the gap. Entry points, `chuzom-onboard`, `chuzom-quickstart`,
`chuzom doctor` and a 60-second README all exist. The gap is **evidence that the documented
path works**, and **two defaults that a launch multiplies by every new user**.

## How the criteria below are written

Every criterion here is falsifiable and mechanically checkable. That constraint is not
style — this audit spent a week on checks that could not fail:

| what it claimed | what it measured |
|---|---|
| G-C "PASS" | 127MB of gitignored files on one disk |
| a quality-guard test | 4,440 rows of the developer's real routing history |
| "hooks cannot block core tools" | the opposite of the shipped behaviour |
| "all file operations are sandboxed" | true of two tools, bypassed by a third |

So: **no criterion is "reviewed", "looks right", or "documented".** Each is a command with
an expected exit code, or a number with a threshold. If a criterion cannot fail, it is not a
criterion.

---

## Step 1 · Prove the documented install path — *highest value, do first*

**Why first.** The README promises `pip install chuzom-router && chuzom install --host
claude-code` and *"Get Started (60 seconds)"*. Those are testable claims and there is no
evidence they are tested. Every other item on this list is a known unknown; this one is an
**unknown unknown**, and it is the first thing every new user meets.

The prior on this is not neutral. Four documented claims examined this week were false.

**Work**

1. Extract every executable command from `README.md` and the quickstart docs — parsed, not
   eyeballed, so a command added later is covered without editing the checker.
2. Run each in a **clean environment**: fresh venv, empty `HOME`, no `~/.chuzom`, no API
   keys, no Ollama. That is the reviewer's machine, not the developer's.
3. Record the real exit code and output of each.
4. Fix the docs where they are wrong, and the code where the docs are right.
5. Keep it as a CI job so the README cannot silently drift from the product.

`docs-code-sync-audit` (agenticgraphs) is built for exactly this shape — extract examples,
execute them, record real exit codes.

**Acceptance criteria**

- [ ] A checked-in script extracts ≥1 command per documented install step and **fails loudly
      if it extracts zero** — a doc-checker that finds nothing passes vacuously, which is
      failure mode #1 above.
- [ ] Every extracted command runs in a clean container/venv with **exit 0**, or is explicitly
      marked non-executable (illustrative snippet) in the doc itself.
- [ ] From `pip install` to a **working MCP connection** — `claude mcp list` shows connected,
      not `CONNECTION_CLOSED` — with **zero** manual steps not in the README.
- [ ] The 60-second claim is **measured**. Either the wall-clock is ≤60s on a clean machine,
      or the README states the real number. Both are fine; an unmeasured claim is not.
- [ ] `chuzom doctor` exits 0 on a clean install with no keys configured, or its non-zero exit
      is documented as expected with the exact remediation printed.
- [ ] The job runs in CI on every push and **fails the build** on drift.
- [ ] It runs on **ubuntu, macos AND windows**, and on the **lowest and highest supported
      Python** (3.11 and 3.14). Added after the fact, and it is the criterion most likely to
      earn its keep: this audit's Windows failure was invisible on every platform reachable
      locally, and the cause — `\"` meaning one thing in bash and another in pwsh — lives in
      exactly the kind of shell-quoted install command this step executes. A single-platform
      install check would repeat that mistake precisely.
- [ ] Each criterion above names **where its proof lives** — the CI job and log — so "it
      worked" is a link, not a recollection. A launch checklist whose evidence is somebody's
      memory of a green run is the same defect as a manifest recording files nobody re-checked.

**Done when:** a reviewer with no prior knowledge, on a clean machine, following only the
README, reaches a working install — and CI proves it stays that way.

---

## Step 2 · The two defaults — *launch multiplies these by every user*

Both are defaults, and a default is a decision made on behalf of everyone who never changes
it. Neither is a bug; both are choices that were never made deliberately.

### 2a · Enforcement blocking core tools

`PreToolUse` blocks `Bash`/`Read`/`Edit`/`Write` in `smart` and `hard` modes. It blocked this
session's own tool calls repeatedly. For a new user, *"I installed this and my tools stopped
working"* is the most likely bad first impression, and the escape valve is not obvious in the
moment of being blocked.

**Question to decide:** what enforcement mode ships as the default for a first-time install?

**Acceptance criteria**

- [ ] The shipped default is **stated in the README**, in the install section, not only in
      configuration docs.
- [ ] A test asserts the default matches what the README says — so the two cannot drift.
- [ ] The block message names the escape valve **and** how to change the default permanently,
      in the message itself. A user who is blocked is not going to go and read docs.
- [ ] A first-install smoke test confirms a new user can run an ordinary `Bash` command within
      their first N interactions under the shipped default, or is told exactly why not.

### 2b · `CHUZOM_DIRECT_EXECUTION` default-on

Grants a local model `write_file`, `edit_file` and `run_command(shell=True)` — unsupervised,
up to 15 iterations, before Claude sees the prompt. Blocklist coverage is **measured at 3/12**
(doc 33, `SECURITY.md`). It stops catastrophic system damage; it does not stop project damage,
credential disclosure, or network exfiltration.

**Recommendation, stated as a judgement:** this should not be on by default at launch. It is
a larger grant than "route my prompts cheaply" implies, and a user who never opts in has no
reason to expect it. Two conservative shapes: agent loop off by default with read-only direct
execution on; or on, without `run_command` in the default tool set.

**Acceptance criteria**

- [ ] A decision is recorded — default-off, reduced-default, or on-with-disclosure — **with
      its reasoning**, by a human, not inferred.
- [ ] If it ships on: the README says so **in the install section**, in the language of what
      it grants ("a local model can run shell commands in your project"), not the language of
      what it is called.
- [ ] `SECURITY.md`'s 3/12 coverage table stays accurate — already enforced by
      `tests/test_direct_execution_blocklist_coverage.py`, which fails if the gap closes.
- [ ] The `agent_loop.py` docstring claiming *"All file operations are sandboxed to the
      project directory"* is corrected. It is false in effect: `run_command` takes arbitrary
      shell, and `cat ../../.ssh/id_rsa` is not a "file operation" the sandbox sees.

---

## Step 3 · mcp 2.0 — decide the timing, then finish or defer

Chuzom is pinned `mcp>=1.0.0,<2` and **works today**; the ceiling did its job. But 2.0 is the
current latest, so launching means shipping pinned behind the current major.

**What the port actually costs — measured, not estimated.** It is *not* the mechanical rename
the downstream attempt suggested:

- `FastMCP` → `MCPServer` (drop-in constructor) — **and** `mcp.server.fastmcp` →
  `mcp.server.mcpserver` across **15 modules**, of which only **one** imports `FastMCP`. The
  other fourteen import `Context`. Porting "the FastMCP importers" misses 14 of 15.
- 2.0 also renamed model fields to snake_case: `Tool.inputSchema` → `input_schema`,
  `InitializeResult.serverInfo` → `server_info`, `protocolVersion` → `protocol_version`.
  **17 Chuzom tests fail** on this alone. Work is stashed on `port/mcp-2.0`, incomplete.

**And a correction to carry forward.** The downstream llm-router port was reported as
*verified* on 2726 passing tests. That repository has **zero** tests referencing `serverInfo`
or `inputSchema`, so its suite could not have detected these renames. That port is
**provisional**, not verified — the green suite measured coverage, not correctness.

**Acceptance criteria**

- [ ] A recorded decision: **port before launch**, or **launch on 1.x** with the pin and the
      reason documented. Either is defensible; drifting is not.
- [ ] If porting: `import chuzom.server` succeeds against a real `mcp>=2.0.0,<3.0.0` install
      **and** the full suite passes — currently 7435 tests, not 7429/17-failing.
- [ ] `tests/test_mcp_dependency_pin.py` ships either way. Its second check parses `from mcp…`
      imports out of the source and asserts each resolves — that is what catches a partial
      port, and it exists precisely because 14 of 15 modules were invisible to the obvious
      grep.
- [ ] The pin and `_SUPPORTED_MAJOR` move in the **same commit** as the imports. The test
      asserts they agree, so they cannot drift.
- [ ] llm-router's port is **re-verified against the renamed fields** before being trusted, or
      re-labelled provisional wherever it is currently described as verified.

---

## Step 4 · CodeQL — record the decision where users can see it

18 alerts on the PR; **zero are new defects**, verified at `(path, rule, line)` against `main`.
One alert is new and is a **false positive created by the path-traversal fix**, because CodeQL
does not model `Path.is_relative_to` as a sanitiser — hardening the code raised the count.

The reasoning exists, in docs 31 and 32. It is in the audit tree, which is not where a
prospective user looks.

**Acceptance criteria**

- [ ] A recorded decision: **merge accepting the red check**, or **triage `main`'s backlog
      first**. Both defensible; the current state — red with no visible reason — is not.
- [ ] If shipping red: `SECURITY.md` states which alerts are open, that none are new, and how
      that was verified. A user evaluating a security tool will look at its security tab.
- [ ] Nothing is dismissed through the API without a written reason. Suppressing an alert is a
      claim that outlives whoever makes it.
- [ ] `continue-on-error` on the CodeQL job is resolved as part of this, not left as a stale
      comment claiming a 403 that no longer happens.

---

## DECISIONS RECORDED — 2026-08-18

Taken by the maintainer. Doc 34's criteria required a recorded decision with reasoning; these
are those decisions, and they now bind the criteria above.

### Step 2b · `CHUZOM_DIRECT_EXECUTION` → **stays ON, with prominent disclosure**

**This goes against the recommendation above**, which argued for default-off. Recorded as the
maintainer's call, not as agreement, so nobody later reads the recommendation and assumes it
was followed.

The consequence is that **the disclosure criterion stops being optional and becomes the thing
that makes this choice defensible.** If it ships on and the README does not say so plainly, the
result is not "a bolder default" — it is an undisclosed grant of shell access. So:

- [ ] README **install section** states, in the language of what it grants: *a local model can
      run shell commands in your project before Claude sees your prompt*. Not the flag's name;
      what it does.
- [ ] The 3/12 coverage figure appears where a user evaluating the risk will see it, not only
      in `SECURITY.md`.
- [ ] `agent_loop.py`'s false *"All file operations are sandboxed"* docstring is corrected —
      **this one is now load-bearing**, because it is the sentence that would reassure a user
      about the exact thing the default exposes them to.

### Step 2a · Enforcement default → **`smart` (unchanged)**

Keeps the routing savings that are the product's reason to exist. The cost is the
first-impression risk named above, which is real but is a UX problem rather than a safety one
— and unlike 2b, a blocked user is inconvenienced rather than exposed.

The block-message criterion remains and is worth more under this choice than under `advise`:
if enforcement ships on, being blocked must be self-explanatory in the moment.

### Step 3 · mcp 2.0 → **finish the port before launch**

Not deferred. So launch is gated on:

- [ ] the snake_case field-rename pass (`inputSchema` → `input_schema`, `serverInfo` →
      `server_info`, `protocolVersion` → `protocol_version`) across the 17 failing tests and
      any code reading those attributes;
- [ ] full suite green against a real `mcp>=2.0.0,<3.0.0` install — 7435, not 7429/17-failing;
- [ ] llm-router's port **re-verified** against the same fields, since its green suite could
      not have detected them.

Work is stashed on `port/mcp-2.0`, incomplete and labelled as such.

### Step 4 · CodeQL — **still open**

The only one of the four without a decision.

---

## Order, and why

1. **Step 1** — converts unknown unknowns into facts, and is cheap. Everything else is a known
   decision; this is the one that can still surprise.
2. **Step 2** — defaults are the highest-leverage thing a launch changes, and 2b has a
   security dimension.
3. **Step 4** — a decision, not work. Can run in parallel.
4. **Step 3** — the largest effort, and the only one where "defer, documented" is a fully
   respectable outcome.

## What "launched" means

All four steps have a recorded outcome — **not all four resolved the same way.** "Launch on
1.x, deliberately, documented" is a pass for Step 3. "Ship red with the reasoning in
SECURITY.md" is a pass for Step 4. What is not a pass is an unmade decision, or a claim in the
README that nobody has executed.
