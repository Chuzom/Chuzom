# 31 · The CodeQL backlog, triaged against the code

**Written 2026-08-18, as the follow-up 30_CI_GAP_PLAN §7 and §9 recorded as owed.**

§7 established that PR #253 introduced **zero** new CodeQL findings — all 14 alerts on the
PR matched `main` at `(path, rule, line)`. That closed the question of whether the PR was at
fault and left the actual question open: *are the 40 alerts on `main` real?*

This is that answer, reached by reading each site and measuring where measurement was
possible, rather than by reading the rule descriptions. A routed model was asked first and
gave the textbook framing for each rule — useful as a checklist, useless for the only
question that matters here, which is whether the inputs are attacker-reachable **in this
codebase**. For a local CLI, "uncontrolled data" often means the user's own config, and
sometimes means a prompt carrying content they never wrote. The difference is the whole
finding.

---

## 1 · Result

40 open alerts on `main` = 22 CodeQL + 18 Bandit. The CodeQL 22:

| verdict | count | |
|---|---|---|
| **Genuine — fixed** | 3 | path traversal → exfiltration; one ReDoS; file-permission window |
| ⚠️ *of those, alerts actually cleared* | 1 | see §5a — the path fix is real but CodeQL cannot see it |
| **Genuine — not exploitable in practice, measured** | 8 | the remaining ReDoS alerts |
| **False positive by construction** | 6 | tests that create the bad condition deliberately |
| **False positive — rule assumes a different threat model** | 2 | hashing |
| **Accepted, low** | 3 | see §5 |

Three real defects, all with a working exploit path demonstrated before the fix and a
regression test with a verified control after it.

---

## 2 · Genuine, fixed

### 2.1 · Path traversal into the provider payload — the serious one

`py/path-injection`, `src/chuzom/code_context.py`.

`extract_code_context` joined `project_dir` with paths pulled from the **prompt**.
`detect_file_paths` requires a code extension but constrains nothing before it, so
`src/../../outside/secret.py` matches and the join resolves outside the project.

What makes this more than a path bug is what happens next: the file is read and **forwarded
to an external provider**. Forwarding context is chuzom's entire function, so an unconfined
join here is an exfiltration primitive — text in a prompt causes an arbitrary `.py`-suffixed
file to be read off the machine and sent to a third party.

Prompt text is not trusted input in the sense the rule assumes. It routinely carries pasted
logs, web content and tool output the user never authored.

Demonstrated before fixing:

```
without confinement : 'sk-live-must-never-be-collected' IS in the returned context
with confinement    : absent
```

Fixed by reusing `is_safe_path` from `capabilities.py`. The real finding is that **one
context-collection path was hardened and its sibling was not** — the check already existed,
with containment, symlink-escape resolution, secret-file patterns and `.ssh`/`.aws`
exclusion. Nobody had applied it here.

### 2.2 · ReDoS in the prompt hook — real, and smaller than it first looked

`py/polynomial-redos`, `src/chuzom/code_context.py`.

`[\w/.-]` contains `.`, so it competes with the following `\.` for every dot and the engine
backtracks quadratically. On one unbroken token: 0.34s at 16k chars, 7.4s at 64k, **69s at
200k** — inside the hook that runs on every prompt.

**The first draft of this finding was wrong and only measuring realistic input caught it.**
The claim was going to be "any large paste hangs the hook." Tracebacks, `pip freeze` output
and logs all run in ~0.001s at 100KB, because whitespace resets the scan and real text is
full of it. The blowup needs a crafted unbroken run of thousands of characters.

So it is a deliberate-input DoS, not the cause of everyday hook slowness — which matters,
because the audit has a documented history of chasing hook stalls, and attaching this to that
story would have been satisfying and false.

Bounding the quantifier at 255 takes 200k chars from 69s to 0.25s, with identical output on
every non-pathological input.

### 2.3 · Secret files world-readable during their first write

Adjacent to `py/clear-text-storage-sensitive-data`, `src/chuzom/hooks/auto-route.py` and
`src/chuzom/dashboard/server.py`. CodeQL flagged the storage; the window is what reading the
code found.

The idiom throughout is `open(...)` → `write(secret)` → `os.chmod(path, 0o600)`. Correct at
rest and wrong in between: `open` creates with the umask default, so on first creation the
file holds its contents at **0644** for the whole write. Permissions are checked at open
time, so a handle obtained in that window survives the chmod.

```
open(path, "a") then chmod : mode while writing = 0o644
open(..., opener=...)      : mode while writing = 0o600
```

13 sites use the pattern; none used an opener. Two were converted — the dashboard **auth
token** and the prompt-transcript shards. The `chmod` stays alongside, because an opener only
applies on creation and cannot repair files written at 0644 by older versions.

The other 11 are deliberately untouched: several write through `_write_json_atomic`, where
the chmod targets a temp path and the rename carries the mode across, and changing those
risks atomicity for no security gain. `paths.private_opener` carries the reasoning so they
can be adopted one at a time.

---

## 3 · Genuine rule, not exploitable here — measured

The other 8 ReDoS alerts (`compaction`, `context`, `context_optimizer`, `okf`, `router`, and
the `bench/` submission) are all **fast under adversarial input**, and the reason is
structural rather than luck.

Every one of them is anchored — `(?:^|\s)`, `^` with `re.MULTILINE`, or a literal prefix like
```` ``` ```` — which limits how many positions can start a match. The one that blew up had
**no anchor**, so all *n* positions were start candidates and the cost went quadratic.

`okf._FILE_PAT` has the same ambiguous character class as the defect in §2.2, and was tested
with input designed to defeat its anchor (many whitespace-separated pathological tokens):

```
one 64k unbroken token       : unanchored 7.660s   okf-anchored 0.001s
800 tokens, 626KB total      :                     okf-anchored 0.011s
```

Left as-is. Bounding them too would be harmless but would imply a risk that was checked and
is not there, and an unexplained defensive edit is how the next reader loses the thread.

---

## 4 · False positives

### 4.1 · Tests that build the bad condition on purpose (6)

`py/overly-permissive-file` × 4 in `tests/test_cluster1_persistence_hardening.py` and
`tests/test_c04_verify_all_hooks.py`: `os.chmod(db_path, 0o644)` followed a few lines later by
`assert stat.S_IMODE(...) == 0o600`. The test loosens permissions **in order to prove the code
tightens them back**. Flagging it flags the hardening.

This is the same shape as the evidence-tree alerts in 30_CI_GAP_PLAN §7 — a scanner correctly
reporting a property of code whose purpose is to exhibit that property.

### 4.2 · Hashing rules assuming password storage (2)

`py/weak-sensitive-data-hashing`:

- `session_store.py` uses SHA-1 with `usedforsecurity=False` **and** a comment stating it is a
  namespacing key. The canonical mitigation is already applied and documented.
- `result_cache.py` uses SHA-256 as a cache dedup key. The rule wants a KDF, which is correct
  advice for credentials and meaningless for a dedup key.

Neither has a fix that would improve anything.

---

## 5 · Accepted, low

- `py/log-injection`, `code_context.py` — a `log.debug` of a path derived from the prompt,
  via lazy `%s` formatting. A crafted path could forge a line in a debug log. Real, trivial.
- 2 × `py/clear-text-logging-sensitive-data` (`doctor.py`, `library-harvest.py`) — diagnostic
  output about whether keys are *set*, not their values.
- 1 × `py/clear-text-storage` in `session_store.py` — session pointer data, already 0600.

---

## 5a · Correction, after CI re-scanned the fixes

Two claims made above and in the commits needed revising once CodeQL ran on the pushed
branch. Recording them here rather than editing them away, because the pattern is the point.

**The alert count went 19 → 18, not 19 → 17.**

| fix | alert outcome |
|---|---|
| §2.2 ReDoS bound | ✅ `code_context.py:147` **cleared** |
| §2.1 path confinement | ❌ alert **persists** (moved to `:281`) **and spawned a second** at `capabilities.py:247` |

**The defect is fixed; the alert is not.** The traversal is genuinely blocked — §2.1's control
demonstrates it directly, `sk-live-...` is absent from the returned context with the
confinement in and present with it out. What CodeQL does not do is recognise
`Path.is_relative_to` as a sanitiser, so the taint from prompt → path survives its analysis
straight through `is_safe_path`, and it now flags both the call site and the helper.

**So hardening the code raised the alert count.** Routing prompt-derived paths through a
shared checker gave CodeQL a new place to find the same unmodelled sanitiser. That is worth
sitting with: on this rule, alert count moves in the opposite direction to security, and
anyone driving the number to zero would be led to revert the fix.

**And a claim from 30_CI_GAP_PLAN §7 no longer holds at the current head.** "This branch
introduces zero new CodeQL findings" was true when measured — verified at
`(path, rule, line)` against `main` — and is now false: `capabilities.py:247` is new, and
`main` has no open alert in that file. It is a false positive introduced by a real fix, which
is a different thing from a regression, but "zero new" is no longer the accurate sentence and
should not be repeated from the earlier document.

The honest summary is therefore narrower than §1 implies: **two defects fixed with the alert
cleared, one defect fixed with the alert remaining and multiplying.** §1's counts describe
defects, not alerts, and the two do not correspond.

**The `CodeQL` check stays red**, and this document does not change that. It explains it.

Nothing here was dismissed through the API. Suppressing an alert is a claim that survives
long after the person who made it, and "a document says why" is a weaker but more honest
artefact than a dismissal reason field nobody re-reads. If the check is to go green, that is
a deliberate decision to dismiss §3 and §4 with these notes attached — 14 of 22 — and it
should be taken by someone who has read them, not as a side effect of this work.

The 18 Bandit alerts (`B310` × 9, `B608` × 7, `B104`, `B108`) are **not** triaged here. `B608`
in particular is SQL-string construction and deserves the same treatment this document gave
the CodeQL 22, which is its own piece of work.

---

## 7 · The method, since it is the transferable part

Three findings came out of 40 alerts. What separated them from the 19 that were noise was
never the rule name or the severity label — 18 of the 21 "high" alerts are not defects.

What worked:

1. **Read the site, then ask what reaches it.** The path-injection alert and the hashing
   alerts have similar severity labels and nothing else in common.
2. **Measure before believing the shape of the bug.** The ReDoS finding was about to be
   reported at roughly ten times its real severity; realistic input corrected it in one
   command.
3. **Measure again after fixing, on the real function.** The permission window was confirmed
   by instrumenting `_append_transcript_shard` and `_get_or_create_token`, not a mock.
4. **Check that the regression test can fail.** The traversal test passed with the fix removed
   — twice, for two different reasons — before it was made honest. Both reasons are recorded
   in its docstring, because that is the part a future editor will otherwise re-discover.
5. **Re-scan after fixing, and believe the result over your own summary.** Two of the three
   fixes did not do what the commit messages said they would do to the alert list, and §5a
   exists because the scanner was checked rather than assumed. The count moved 19 → 18 where
   the write-up implied 17, and one fix *added* an alert.

And the finding that outranks the individual fixes: **alert count is not a security metric on
this rule set.** Fixing the traversal raised it. Six alerts are tests proving the hardening
works. Anyone optimising the number would revert the first and delete the second.
