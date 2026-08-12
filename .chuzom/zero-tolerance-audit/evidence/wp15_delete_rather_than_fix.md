# WP-15 — delete rather than fix

Date: 2026-08-12. Findings RED3-10, RED6-04, RED6-07, RED8-06, RED8-10.

---

## Deleted (both verified by measurement to have zero production callers)

**`response_validation.py`** (249 lines) + its test. Its docstring claimed to
"prevent code injection or malicious payload processing". Nothing imported it.
Dead safety code is worse than none: an auditor counts a defence that never runs,
and the module's existence is itself evidence that someone believed the risk was
covered.

**`secret_scrubber.scrub_environment()`** + its tests. Zero callers, and a
**narrower** allowlist than the live path (`safe_subprocess`'s, from WP-01). So it
read as defence-in-depth while contributing nothing, and had it ever been wired
up it would have been the weaker of the two.

## RED8-06 — one task→tool map

Three independently-maintained maps:

| | keys | fallback |
|---|---|---|
| `auto-route.py::TOOL_MAP` | 8 | `llm_route` |
| `agent-route.py::_TOOL_MAP` | 5 | **`llm_analyze`** |
| `service.py` inline dict | 5 | `llm_route` |

The five shared keys agreed, so the maps looked consistent on inspection. The
divergence was in what happened to **everything else**: an ambiguous prompt that
`auto-route` sent to `llm_route` — which can pick a tool — was sent by
`agent-route` to `llm_analyze`, a completion door that **cannot run tools**.
NORTH_STAR names that outcome as its first anti-goal, "a structural dead-end".

No test drove one prompt through all three, which is how they drifted while every
unit test passed.

The canonical map now lives in `tool_surface.py` because that module is
deliberately dependency-free and loadable by path — a hook running under a bare
`python3` with no chuzom importable can still read it. That constraint is exactly
**why** the copies existed, so putting the canonical version anywhere else would
have recreated them. Verified: `tool_for_task('bogus')` → `llm_route`, was
`llm_analyze`.

`service.py`'s function is **kept** and now delegates: `service.py:239` calls it,
so it is a live sidecar endpoint, not dead code. Only the private map is gone.

## RED6-04 — one public-bind gate, not three patches

Four components bind a socket and serve real, paid model calls. **One** refused a
wildcard bind without an explicit opt-in; three did not.

- `gateway.py` — a whole-file grep for `Depends(` returns **zero**. Its only
  protection is `_guard_cross_origin`, a browser CSRF/DNS-rebinding `Host` check
  whose own docstring says "legitimate CLI/SDK clients (curl, openai SDK) send a
  loopback Host and no browser Origin, so they are unaffected" — by explicit
  design it admits exactly the traffic shape any non-browser process produces.
- `route_server.py` — console script `chuzom-route`, zero auth checks.
- `commands/admin_api.py` — help text advertises `--host 0.0.0.0` with a prose
  security note. A note is not a gate: the operator has typed the flag by the
  time they could read it.

**This is one missing abstraction, not three bugs.** Three components forgot and
one remembered, which is the expected outcome of a convention each new server has
to re-implement. `net_bind.py` turns "remember the gate" into "call the helper",
and a source-level test asserts every serving module calls it, so the next server
someone adds fails a test rather than a network. `server.py` now delegates rather
than keeping the one correct private copy — keeping it private is precisely the
arrangement that produced three misses out of four.

**The gate is NOT authentication**, and says so. It refuses an unattended public
bind; it does nothing about an attacker already on loopback, and `gateway.py`
still has zero `Depends(`. Fails closed on unrecognised values, so a typo leaves
you on localhost. Legacy `CHUZOM_SSE_ALLOW_PUBLIC` still honoured — consolidating
a gate must not silently revoke an opt-in somebody relies on.

## RED8-10 — env registry, and the circularity it had to avoid

195 variables read across 313 sites, nothing declaring them. The audit counted
186; by measurement here it was 195 and nobody had noticed the drift.

**The registry is a checked-in literal; the AST scan is independent ground truth.**
Generating it from the scan and validating with that same scan would pass
unconditionally — the identical trap already found twice in this codebase:

- `tool_surface.unregistered()` validated tier constants against `_TIERS`, which
  **is** the tier constants. A bogus tool name passed lint and 106 tests, and
  Q3(c) was recorded CLOSED on that basis.
- `scripts/lint_tool_surface.py` checks emitters against emitters and reports
  clean under the same mutation.

Both looked like validation.

**Two things the registry's own tests caught immediately:**

1. **It went stale within the same session.** `CHUZOM_ALLOW_PUBLIC_BIND` was
   missing because the inventory predated `net_bind.py`. Caught on first run —
   which is the drift the registry exists to stop.
2. **The scanner has a structural blind spot.** `net_bind.py` reads via a
   variable (`for env in (A, B): os.environ.get(env)`), and a scan matching only
   literal arguments cannot see it. The two indirect reads are declared by hand
   and exempted via `_INDIRECT_READS`, with a test pinning the limit and an
   instruction to keep the list short — every entry is a hole in the scan.

Stating the blind spot matters more than the registry: a registry that silently
under-reports its own surface is the same failure class as the guards above.

## Three claims corrected by measurement

Recorded so a re-auditor does not re-derive them, and because two of the three
would have caused a wrong action:

1. **"Delete two of three duplicate classifiers"** (plan). Does NOT mean
   `classifier.py` / `classify.py` / `semantic_classify.py` — all three have live
   production importers and form a pipeline (`classify.py` imports both others).
   Deleting two would have broken routing. RED8-06's subject is the three
   classifier+TOOL_MAP **pairs**.
2. **"presets.py ships a built-in team-server preset with host 0.0.0.0"**
   (10_SECURITY_AUDIT). **False.** Measured: `_DEFAULTS` holds only `local` at
   127.0.0.1; `bind()` returns `('127.0.0.1', 17900)` with no presets.yaml; and
   `team-server` appears exactly once, in the module **docstring**, as an example
   of a user-authored file. 14_FINDINGS' own downgrade note ("requires a
   deliberately-chosen, undocumented non-default preset") is the accurate
   version. The docstring was still worth fixing — it is where a user learns the
   format, and it demonstrated a wildcard bind as ordinary practice.
3. **`main_sse()` is not a live public bind.** Deliberately retained, unexposed,
   and guarded by `tests/test_no_chuzom_sse_entry_point.py`, which asserts it
   keeps its SEC-001 warning. Nearly reported as an unauthenticated public bind.

## A test that asserted the defect

`test_admin_api_cli.py::test_valid_flags_invoke_uvicorn` passed `--host 0.0.0.0`
and asserted `rc == 0`. Its purpose is flag parsing — `0.0.0.0` was an incidental
distinctive value — but as written it pinned an unauthenticated wildcard bind as
correct behaviour. It now opts in explicitly, keeping the parsing assertion while
documenting that the gate is bypassable on purpose.

That is the **third** test found this session asserting a defect as the contract,
after `test_savings_never_negative_in_display` (the clamp that hid overspend) and
the budget-cap test (a premise that breaks under load). A test can be green,
meaningful, and pointed the wrong way — so when a fix breaks a test, read what
the test asserts before assuming the fix is wrong.

## CI wiring — deliberately NOT a lint script

The fail-open and tool-surface guards are lint-job steps because neither is a
test. The env registry check **is** a test, and CI's `uv run pytest tests/ -q`
already collects it, so it is enforced today.

A lint script was considered and **rejected**: it would need a scanner, making a
third implementation alongside the registry literal and the test's scanner. Each
copy is a place the ground truth can diverge, and the whole design of this
registry is that the declaration and the scan must be *different artifacts*. The
gain would have been earlier failure in a fast job; the cost is a third thing to
keep honest. Not worth it.

Recorded as a decision rather than left silent, because "the other two guards are
in CI's lint job and this one isn't" otherwise reads as an oversight.
