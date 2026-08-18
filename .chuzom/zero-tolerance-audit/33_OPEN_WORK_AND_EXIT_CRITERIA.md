# 33 · Open work, and what "done" means for PR #253

**Written 2026-08-18.** Docs 30–32 each closed a specific investigation. This one does
something different: it is the **single list of what is still open**, across both
repositories, with an explicit exit condition for the PR — because the work has now branched
far enough from "fix eleven CI failures" that the finish line needs stating rather than
assuming.

Status vocabulary, used strictly:

| | |
|---|---|
| **VERIFIED** | fixed, with a control proving the test fails without the fix |
| **DONE, UNVERIFIED** | changed, not yet confirmed by CI or a control |
| **DIAGNOSED** | cause established, fix not written |
| **REPORTED** | claim received, not yet checked against the code |
| **DECISION** | not a defect — needs a human to choose |

---

## 1 · The blocking item

### C1 · Chuzom is red, and it is mine · **DIAGNOSED**

`f8b0a02` broke `quality-gates` and `test (3.14)` after five consecutive green runs. All ten
errors are identical: `execution_ledger.py record_event → conn.commit()`, `Failed: Timeout
(>30.0s)`, at **setup**, not an assertion.

**Diagnosed cause.** `_connect()` sets SQLite `timeout=30.0`; CI runs `pytest --timeout=30`.
They are equal, so the instant any commit enters SQLite's busy-wait, pytest-timeout kills the
test *while SQLite is still legitimately waiting*. The comment above that line records the
busy-timeout being **raised** from 5s to 30s to survive "pathological CI-runner load" — raised
to exactly the test timeout, which guaranteed this collision. Two constraints, each sensible,
never cross-checked against each other.

**Not established, and I will not claim it:** the causal link from the `_load_rows` change to
the extra contention. Those new tests write to `tmp_path` databases while the soak tests use
the default `_db_path()` — different files, so it is not direct lock contention. The timing is
damning; the mechanism is not proven.

**Fix the collision, do not revert the hardening.** `_load_rows`'s structured filters removed a
real injection hazard and its tests pass. Reverting would restore the hazard to fix a timeout.

Exit: reproduce locally with `pytest tests/soak/ --timeout=30`, make the two timeouts unequal
(and add a guard that they can never again be equal — this is the third "two settings that
must disagree" defect this week), confirm green.

---

## 2 · Decisions that are not mine to make

### C2 · CodeQL stays red · **DECISION**

18 alerts on the PR. Measured at `(path, rule, line)` against `main`: **zero are new defects.**
One *is* new — `capabilities.py:247`, a false positive **created by the path-traversal fix**,
because CodeQL does not model `Path.is_relative_to` as a sanitiser. Hardening the code raised
the alert count (doc 31 §5a).

Merging means accepting a red check whose redness has been measured rather than argued.
Declining is equally defensible. The answer to it is triaging `main`'s backlog — **not**
anything further in this PR. Nothing has been dismissed through the API: suppressing an alert
is a claim that outlives whoever makes it.

### C6 · `continue-on-error` on the CodeQL job · **DECISION**, blocked on C2

Its comment is stale — code scanning is enabled and SARIF uploads succeed. Kept deliberately:
removing it today makes CodeQL block on `main`'s backlog rather than on new findings. Unblocks
once C2 is decided.

---

## 3 · Chuzom · known-outstanding, non-blocking

| | item | status | note |
|---|---|---|---|
| C3 | 540s watchdog is marginal | **DIAGNOSED** | flaked once today with **zero** failing tests; will recur. Raise it, or make the re-run automatic |
| C4 | 11 of 13 sites still `open()`-then-`chmod` | **DECISION** | the two secret-bearing ones are converted. Several others write via `_write_json_atomic`, where the chmod targets a temp path — converting those risks atomicity for no security gain. `paths.private_opener` carries the reasoning |
| C5 | 4 gitignored `.db` captures unverifiable | **won't fix** | hashes recorded, not gated. 127MB of a user's real usage data cannot go in a public repo |

---

## 4 · llm-router · five reports

### L1 · `mcp` unbounded → total install breakage · ~~VERIFIED~~ **PROVISIONAL**

`mcp>=1.0.0` with no ceiling; `mcp 2.0.0` — the current latest — removed
`mcp.server.fastmcp`, so **every fresh install** died at import. Client reports
`CONNECTION_CLOSED`, indistinguishable from a network fault.

Two commits, deliberately a sequence rather than alternatives:

- `b3f22b4` — pin `<2.0.0`. The immediate unblock.
- `22bb7fc` — **port to the 2.0.0 API** (`MCPServer`), pin moved to `>=2.0.0,<3.0.0`.

**12 modules, not the 7 that imported `FastMCP`** — five more imported `Context` from the same
removed package. Verified against a real 2.0.0 install: server imports, registers 17 tools,
**2726 passed / 0 failed**.

⚠️ **Downgraded from VERIFIED on 2026-08-18.** The 2726-passing suite did not demonstrate the
port was complete — it demonstrated that llm-router has **zero tests referencing `serverInfo`
or `inputSchema`**, the fields mcp 2.0.0 renamed to snake_case. Porting Chuzom later hit
exactly those renames and failed 17 tests. That suite measured coverage, not correctness.

Re-verifying it against the renamed fields is a launch criterion (doc 34 Step 3). Until then
this reads as provisional, which is the honest label — a green suite is evidence only about
what the suite exercises.

### L2 · SECURITY.md claims hooks cannot block core tools · **REPORTED, informally confirmed**

Lines 126–127 and 168 assert *"Hooks cannot block core tools (Read, Edit, Bash) — would create
deadlock."* This is false: the enforce-route hook blocked `Bash` on me **repeatedly during this
session**, with a violation counter and auto-pivot. v13 removed an older exemption specifically
to make blocking stricter.

The reporter's distinction is the right one: *no permanent lockout* is true; *cannot block* is
false. In a security document that is the difference between a guarantee and its opposite.
Reword to what is actually guaranteed, plus a test asserting the doc matches hook behaviour.

### L3 · `agoragentic` registered unconditionally · **REPORTED — and it is a port gap**

Four tools handling **real USDC settlement on Base L2** and dispatch to dynamically-matched,
unvetted providers, exposed to every install.

**Chuzom already has the fix**: `tools/agoragentic.py:215`, SEC-003 — off unless
`CHUZOM_AGORAGENTIC=on`, with the wallet/marketplace reasoning written out. So this is not a
design question, it is an unported mitigation.

Which makes it doc 32 §5's pattern **one level up**: not "a helper exists and a sibling path
skipped it", but "a mitigation exists and the *downstream repository* never received it". Port
it, then **sweep for other unported `SEC-*` mitigations** — that sweep is worth more than the
single fix.

### L4 · `DIRECT_EXECUTION` default-on with unsupervised shell · **REPORTED, unverified**

Claim: defaults true; `agent_loop.py` hands a local model `write_file`/`edit_file`/
`run_command(shell=True)` unsupervised, up to 15 iterations, before Claude sees the prompt.
Blocklist covers only top-level destructive patterns.

**Verify before characterising.** Three findings this week shrank on measurement (doc 31 §2.2,
doc 32 §2.2, doc 31 §5a). Measure the blocklist's actual coverage, then write the threat-model
entry and assess whether default-on is right.

### L5 · Stop hook fires every turn · **REPORTED**

Full boxed summary after every response, hardcoded, no toggle. Only workaround is deleting the
hook registration, which loses the information entirely.

Add `LLM_ROUTER_STOP_HOOK`: `full` | `condensed` | `disabled`. The reporter suggests
`condensed` as the new default; **decide deliberately and say why** — changing a default is a
change to everyone's experience, and "the reporter suggested it" is not a reason.

---

## 5 · Recommended order

Sequenced by *who is hurt now*, not by difficulty:

1. **L1 push** — users are broken today; the fix is done and verified. Nothing outranks this.
2. **C1** — Chuzom is red and I broke it.
3. **L3** — money and third-party data exposed by default.
4. **L2** — false claim in a security document.
5. **L4** — verify, then document.
6. **C2/C6** — the CodeQL decision, once someone has read doc 31 §3–§4.
7. **L5, C3, C4** — real, and none of them are hurting anyone.

---

## 6 · Exit criteria for PR #253

The PR is done when **all** of these hold. Anything not on this list is explicitly out of scope
and belongs in a follow-up.

- [ ] **All eleven original CI failures resolved** — currently true; §30 documents each.
- [ ] **`quality-gates` and `test (3.14)` green again** (C1). The PR may not merge having broken
      gates that were passing when it opened.
- [ ] **No new CodeQL defect** — verified at `(path, rule, line)`. Currently true. The one new
      alert is a false positive created by a real fix, recorded in doc 31 §5a.
- [ ] **CodeQL's red status is a recorded decision**, not an unexplained failure (C2), with doc
      31 §3–§4 attached.
- [ ] **Every fix has a control** proving its test fails without it. Currently true for all
      seven landed fixes.
- [ ] **G-C green in a clean clone** — the gate that had never once passed.
- [ ] **Every audit document corrected where later work refuted it.** Docs 31 and 32 both carry
      corrections; a document that quietly stops being true is worse than no document.

**Explicitly NOT exit criteria**, so they cannot be used to hold the PR open indefinitely:
`main`'s 40-alert backlog, the llm-router items (a different repository), C3/C4/C5, and the
540s watchdog.

---

## 7 · The thing worth carrying forward

Four genuine defects came out of 40 scanner alerts, and **three had the same shape**: a
correct, tested, documented mitigation already in the repository, and a parallel path that
never used it. L3 makes it four, one level up.

No scanner names this shape, because each reasons about a site rather than about two sites that
should agree. The question that found all four costs nothing:

> **Is there already a helper for this, and does everything that needs it use it?**

And the corollary, which this session demonstrated three times: **writing the check finds more
than reading the code.** `lint_suite_env_parity` found the G-D gap; `lint_workflow_shell_portability`
reproduced the Windows failure exactly; `lint_ollama_url_readers` found four unvalidated
readers and refuted the document it was written to support. A check must be right about every
instance; a reader only has to feel right about the ones they looked at.
