# 32 · The Bandit backlog, triaged against the code

**Written 2026-08-18. Completes the work 31_CODEQL_TRIAGE §6 named and explicitly declined
to do: "The 18 Bandit alerts are not triaged here. B608 in particular is SQL-string
construction and deserves the same treatment."**

Same method as doc 31 — read every site, measure or demonstrate where possible, and treat the
rule description as a checklist rather than a verdict. A routed model was asked first and
returned the textbook framing for each rule; it called B608 and B310 "genuine risk"
unconditionally, which is right in general and wrong for 15 of the 16 sites here. The
question a rule cannot answer is *what reaches this code in this program*.

---

## 1 · Result

| verdict | count | |
|---|---|---|
| **Genuine — fixed** | 1 | B310: CHZ-SEC-06 bypassed by two duplicate URL readers |
| **False positive** | 17 | B608 × 7, B310 × 8, B104, B108 |

One defect in eighteen alerts. It is the same defect **shape** as doc 31's most serious
finding, which is the reason this document is worth more than its hit rate suggests.

---

## 2 · The one real defect · B310

`src/chuzom/hooks/agent_loop.py`, `src/chuzom/hooks/direct_executor.py`.

`config.validate_ollama_url` exists because these environment variables were an SSRF sink.
Its own docstring records the fix: `CHUZOM_OLLAMA_URL`/`OLLAMA_URL` *"reached `urlopen` with
no scheme or host validation, so `file://` was accepted (local file read) and cloud-metadata
addresses were attempted — a classic SSRF sink."*

That fix landed in `config.py`. Both hook modules kept **their own copies of the same
reader**, unvalidated, so whichever path ran first decided whether the protection applied:

| input | validator | hook readers |
|---|---|---|
| `file:///etc/passwd` | BLOCKED | allowed |
| `http://169.254.169.254/latest/meta-data/` | BLOCKED | allowed |
| `http://some-external-host` | allowed | allowed — *by design* |

Reachable with no local access: `_load_dotenv` in `auto-route.py` reads `Path.cwd()/".env"`,
so **a cloned repository can set the variable**.

Both readers now use the canonical validator, imported rather than reimplemented, failing
**closed** to localhost — refusing to reach a configured Ollama is a degraded feature, while
honouring an unvalidated one is the defect.

### 2.1 · A suppression built on a false premise

`direct_executor.py` carried:

```python
with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 — localhost only
```

It is not localhost only. The URL comes from the environment. **The justification was the
thing that made the alert invisible**, and it was wrong — which is worse than no suppression,
because a bare alert gets re-examined and a confidently-annotated one does not. This is the
`nosec` equivalent of the manifest that recorded files that were never in the repository
(30_CI_GAP_PLAN §3): bookkeeping asserting a fact nobody re-checked.

Worth a sweep of the other `nosec`/`noqa` justifications in this codebase on the same
grounds. Not done here.

### 2.2 · Where the first write-up was wrong

The initial framing was "prompts can be redirected to an arbitrary host". Then the validator
was actually run: it returns arbitrary `http(s)` hosts **unchanged**, rejecting only
non-http schemes and metadata/link-local addresses. A remote Ollama is a supported
configuration.

So the gap is two cases, not three. **The third time in this session that a finding shrank
the moment it was measured** — see 31 §2.2 for the ReDoS and 31 §5a for the alert counts.
The recurrence is the finding: the first framing of a security issue is reliably the most
alarming one available, and the measurement always came cheap.

---

## 3 · B608 × 7 — SQL injection, all false

Every flagged site interpolates into SQL, and in every one the interpolated fragment is
composed from **literals only**, with user values passed as `?` parameters.

- **`cost.py`, `session_spend.py`, `execution_ledger.py`** — `f"… WHERE {where}"`, where
  `where` is built by appending literal predicates (`" AND task_type = ?"`) and pushing values
  into `params`.
- **`cost.py:1160` group** — `where` comes from `{...}.get(period, "")`, a dict of four
  literal clauses. An arbitrary `period` selects a literal or the empty string; it cannot
  reach the query.
- **`cost.py:539`** — the only site interpolating an identifier, `pragma_table_info('{table}')`,
  and it is preceded by an explicit allowlist of nine table names with a comment saying why.
  The column is parameterised.
- **`execution_ledger._load_rows(where, params)`** — takes the clause as an argument, so
  safety is a property of callers rather than of the function. All four pass string literals.

**The one thing worth flagging**: `_load_rows` is the fragile spot. It is safe today and its
signature invites an f-string. Not changed — a runtime check cannot distinguish a literal from
an interpolation, so the honest options are a docstring contract or a lint, and neither was
worth adding without a second caller to justify it. Recorded here so the next person adding a
caller has been told.

---

## 4 · B310 × 8 remaining, B104, B108 — false

- **B310 elsewhere** (`alerts.py`, `semantic_classify.py`, `config.py:probe_pxpipe`,
  `doctor.py`, `library/sealer.py`, `hooks/session-start.py`, `agentic/react.py`) — these
  reach either a validated URL or a localhost probe. The rule fires on `urlopen` itself.
- **B104** (`config.py`) — `"0.0.0.0"` appears inside `_BLOCKED_HOSTS`, a **denylist** used to
  reject SSRF targets. Bandit reads the literal as "binds all interfaces"; it is the exact
  opposite. Flagging it flags the mitigation — the same shape as the `chmod 0o644` tests in
  doc 31 §4.1 and the evidence-tree PoC in 30_CI_GAP_PLAN §7. **Three separate scanners have
  now flagged a protection because it mentions the thing it protects against.**
- **B108** (`agentic/worktree.py`) — `f"/tmp/wt/{name}"` inside `FakeWorktreeOps`, documented
  as "In-memory worktree ops for tests". It returns a string and never touches disk.

---

## 5 · The pattern across both documents

Docs 31 and 32 found four genuine defects in 40 alerts. **Three of the four are the same
shape**, and it is not a shape either scanner names:

| | hardened | left behind |
|---|---|---|
| path confinement | `capabilities.is_safe_path` | `code_context` collected prompt paths unchecked |
| URL validation | `config.validate_ollama_url` | two hook modules read the env directly |
| file permissions | *(nothing)* | 13 sites created secret files at 0644, then chmod'd |

A security fix is applied where the bug was reported and not to the parallel path that does
the same job. Every one of these had a correct, tested, documented mitigation sitting in the
repository already — the defect was that something else did not use it.

Neither Bandit nor CodeQL can see this, because both reason about a site rather than about
two sites that should agree. What finds it is asking, at each alert: **is there already a
helper for this, and does everything that needs it use it?** That question found three of the
four defects and cost nothing.

The corollary for fixing: `is_safe_path` and `validate_ollama_url` were both *imported* rather
than reimplemented at the second site, and the permission fix went into `paths.py` rather than
inline. A fourth copy of the rules would eventually diverge in exactly the way the second and
third did.

---

## 6 · What is not done

- **`nosec`/`noqa` justification sweep** (§2.1). One was checked and was false. The others are
  unexamined, and a false justification is a defect that hides a defect.
- **`_load_rows`'s signature** (§3).
- **Nothing dismissed through the API**, same position as doc 31 §6. Bandit alerts remain
  open with this document as the reasoning.
