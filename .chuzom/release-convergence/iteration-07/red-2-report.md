# RED-2 (CUSTOMER-REALITY) — Iteration 7 Independent Audit

Commit under audit: `611c506`. Worked independently; did not read RED-1's iteration-7 output or any
other iteration-7 auditor artifact before forming these findings.

## Summary

| ID | Severity | Title |
|---|---|---|
| RED2-7-01 | **High** | `chuzom-install-hooks uninstall` (frozen public entry point) still leaves a full claw-code + IDE-config install behind — the exact RED2-6-02 defect, unfixed in a sibling command |
| RED2-7-02 | **High** | README claims-honesty carve-out is section-scoped, not claim-scoped — an unrelated unqualified magnitude claim smuggled into the disclaimed "Estimated savings" block passes the guard test suite undetected |

2 High. No Critical. No additional core-Medium findings met the reproducibility/impact bar.

---

## RED2-7-01 — `chuzom-install-hooks uninstall` does not clean claw-code or IDE configs

**Severity:** High (same rating as the original RED2-6-02, which this reproduces in a sibling code path)

**Surface:** `src/chuzom/install_hooks.py::main()`, uninstall branch (~line 1270-1285); contrast with the
FIXED path at `src/chuzom/commands/uninstall.py::_run_uninstall()` (lines 46-73).

**User-experience vs. truth:** The iteration-6 report claimed "wired uninstall to clean claw-code +
IDE configs" (RED2-6-02, High, marked fixed). That is true **only** for `chuzom uninstall`. It is false
for `chuzom-install-hooks uninstall`, a second, independently pip-installed console script that:

- is registered as a real entry point in `pyproject.toml` (`chuzom-install-hooks = "chuzom.install_hooks:main"`, lines 128-131);
- is explicitly declared a **frozen, supported public CLI entry point** in `CHANGELOG.md:1528` ("Removals will go through a deprecation cycle in 0.2.x") — not vestigial code;
- is the exact command the tool's own install output tells the user to run: `install_hooks.py:1297` prints `"To uninstall: chuzom-install-hooks uninstall"` immediately after every `chuzom-install-hooks` install. Anyone who installs via the bare script (rather than the README-documented `chuzom install`) is funneled straight into the broken path by the product itself.

`main()`'s uninstall branch calls only `uninstall()` — never `uninstall_claw_code()` or
`uninstall_ide_configs()`. The existing regression test (`tests/test_red2_6_02_uninstall_cli_wiring.py`)
only exercises `commands/uninstall.py::_run_uninstall()`, so this sibling gap was never covered.

**CONFIRMED — full E2E repro** (tmp `$HOME`, `.venv/bin/python`, no repo pollution):

1. Seeded `$TMPHOME/.claw-code/settings.json` with `{}` (required for claw-code detection).
2. `HOME="$TMPHOME" .venv/bin/python -m chuzom.install_hooks` — primary install.
3. `ih.install_claw_code()` directly — confirmed 12 hooks + 2 sidecars in `$TMPHOME/.claw-code/hooks/`, `CHUZOM_CLAW_CODE=true` in `.claw-code/.env`, full live MCP registration (all 6 hook events) in `.claw-code/settings.json`.
4. `ih.install_ide_configs(Path("$TMPHOME/proj"))` — confirmed `.vscode/mcp.json`, `.windsurf/mcp.json`, `.cursor/rules/use-chuzom.mdc` written.
5. `HOME="$TMPHOME" .venv/bin/python -m chuzom.install_hooks uninstall` — output confirmed cleanup of all primary Claude Code surfaces (12 hooks, settings.json/`.claude.json` MCP entries, rules, statusline, Claude Desktop config), but printed **nothing** about claw-code or IDE configs.
6. Post-uninstall verification: **all** claw-code state survived untouched — 14 files in `.claw-code/hooks/`, `CHUZOM_CLAW_CODE=true` still set, full live MCP registration still in `.claw-code/settings.json` — and all 3 IDE config files in `$TMPHOME/proj` were untouched.

Net effect: a user who runs `chuzom-install-hooks uninstall` (as instructed by the tool itself) is told
"Done." while a fully live, auto-routing claw-code integration and MCP server registration remain active
on next claw-code session, and stale IDE `mcp.json`/Cursor-rule files remain in their project.

**Suggested fix:** Make `install_hooks.py::main()`'s uninstall branch call the same three removers as
`commands/uninstall.py::_run_uninstall()` (ideally by having one delegate to the other, so this class of
drift structurally can't recur), and extend `test_red2_6_02_uninstall_cli_wiring.py` (or a sibling test)
to cover the `chuzom-install-hooks` entry point directly.

---

## RED2-7-02 — README claims-honesty carve-out is abusable (section-scoped, not claim-scoped)

**Severity:** High

**Surface:** `tests/test_claims_no_fabricated_magnitudes.py::_readme_scannable_text()` (lines 100-119),
which gates `test_readme_full_has_no_unqualified_magnitude_claims` — the guard whose entire job is to
stop unqualified magnitude claims from reappearing in `README.md` (the single most user-facing surface,
per the task's own priority framing and per RED2-5-04 in the prior iteration).

**User-experience vs. truth:** The carve-out logic finds the `### Estimated savings by workload` heading
and exempts **everything from that heading up to the next `## `/`### ` heading** from the
`MAGNITUDE_FORBIDDEN` regex scan, provided the disclaimer string `"illustrative estimates — directional,
not measured"` appears **anywhere within that whole block**. The exemption is granted at
section-granularity, not at the granularity of the specific disclaimed figures. Nothing ties the
disclaimer to the individual claims it's supposed to qualify — any additional prose added later inside
that same heading-to-heading span inherits the exemption "for free," even if it makes a completely
unrelated, unqualified, absolute claim.

**CONFIRMED — reproduced by actually running the guard test suite:**

1. Took a working copy of `README.md` and inserted, immediately before the existing
   `"**Why agentic saves the most:**"` sentence (inside the already-disclaimed "Estimated savings by
   workload" section, well after the disclaimer paragraph), this fabricated sentence:
   > "Independent benchmarks show Chuzom is a flat **100x cheaper** and delivers **50-100x less** latency
   > than calling Claude directly, in every case."
2. Ran `.venv/bin/python -m pytest tests/test_claims_no_fabricated_magnitudes.py -q`.
3. **Result: all 6 tests passed (100%)**, including `test_readme_full_has_no_unqualified_magnitude_claims`
   — the exact test whose stated purpose (per its own docstring/RED2-5-04 comment) is to catch
   unqualified `NNx`/`NN-NNx` claims anywhere in the README.
4. Reverted (`git checkout -- README.md`); confirmed clean via `git status --porcelain -- README.md`.

The current, real README content is clean — this is not a live user-facing defect today. It is a
structural weakness in the enforcement mechanism guarding the highest-traffic honesty surface: a future
PR that adds unqualified marketing copy anywhere inside that one heading-to-heading span (the most
"credible-looking" place to hide it, since it sits next to a real disclaimer) will not be caught by CI,
silently shipping to every user who reads the README.

**Suggested fix:** Scope the exemption to only the specific disclaimed figures (e.g. exempt only the
table rows/cells that carry the audited-ratio methodology, or require the disclaimer to appear within N
lines of each matched claim) rather than the whole heading-to-next-heading span. At minimum, add a
regression test (mirroring the repro above) that asserts an *injected* unrelated claim inside the
disclaimed block is caught, to close the exact gap this finding demonstrates.

---

## Iteration-6 fixes: verification results (no bypass found)

### RED2-6-01 / RED2-6-03 (content-aware hook/rules self-heal) — VERIFIED FIXED

Full E2E against a tmp `$HOME` subprocess (not just unit-test mocks):

- Installed via `chuzom.install_hooks`, then tampered the installed `chuzom-auto-route.py` by replacing
  every literal `0o600` with `0o644` (i.e., simulating the exact pre-fix, security-relevant regressed
  content) while leaving the `# chuzom-hook-version:` stamp untouched — the precise "content drift, same
  stamp" scenario RED2-6-01 targets.
- `check_and_update_hooks()` call 1: emitted `"Refreshed chuzom-auto-route.py (content drift at v27)"`
  and the installed file became **byte-identical** to bundled again — i.e., the real `0o600` chmod calls
  and `_scrub_secrets_text` logic were restored, not just re-stamped.
- `check_and_update_hooks()` call 2 (immediately after): **no-op**, `[]` — confirms it does not
  thrash/re-copy on every startup once converged.
- Confirmed `_files_differ()` is a pure byte comparison (`src.read_bytes() != dst.read_bytes()`), so any
  line-ending (CRLF/LF) drift is caught by construction (byte-for-byte differs → refresh triggers) — no
  separate repro needed beyond the mechanism inspection.
- Edge case found and evaluated, **not reportable**: `_files_differ` compares content bytes only, not
  file permissions. Reproduced a scenario where content is already byte-identical to bundled but the
  executable bit was stripped (`chmod 0644`) — `check_and_update_hooks()` correctly treats this as a
  no-op (no content drift) and does **not** restore the exec bit. However, hooks are invoked as
  `<python-interpreter> <script-path>` (confirmed via the installed `settings.json` hook `command`
  strings), i.e., interpreter-invoked rather than relying on the file's own shebang + exec bit — so a
  stripped exec bit has no effect on actual hook execution. No real user impact; excluded per the
  Low/style exclusion in scope.

### RED2-6-02 (uninstall wiring) — VERIFIED FIXED for `chuzom uninstall`, BROKEN for `chuzom-install-hooks uninstall`

See RED2-7-01 above. The documented, README-referenced path (`chuzom install` / `chuzom uninstall`) is
correctly fixed and was re-verified via `commands/uninstall.py` source read (calls all three removers,
each independently exception-guarded so an optional-surface failure never aborts the uninstall).

### RED2-2-02 / RED2-3-01 (cap_downgraded telemetry honesty) — spot-checked, fine

`ModelResponse._cap_downgrade_target()` (`src/chuzom/types.py:544-551`) correctly distinguishes a
soft-cap fallthrough to paid Anthropic ("Claude (subscription)") from an actual free/local downgrade
("a free/local model"), consistent with its RED2-3-01 fix comment. `summary()`/`header()` both render
this honestly when `cap_downgraded` is set. No new issue.

### RED2-5-03 (pre-flight banner honesty) — spot-checked, fine

`_preflight_check()` in `src/chuzom/hooks/session-start.py:724-760` correctly distinguishes "zero usable
routing paths" (actionable) from "one optional provider unconfigured" (informational, never told to
"fix"). This matches the live SessionStart banner observed during this audit session itself
("Optional providers not configured: Gemini — routing works via OpenAI, Anthropic (subscription),
Ollama."). No new issue.

### `~/.chuzom/` leftover after plain `uninstall` (no `--purge`) — investigated, not elevated

`uninstall()` never touches `~/.chuzom/` (usage DB, `.env` with API keys, `agentic_models.json`); only
`chuzom uninstall --purge` removes it, gated behind an explicit confirmation prompt that lists every file
about to be deleted. This is disclosed accurately in `chuzom --help`
(`cli.py:24`: "chuzom uninstall --purge — also delete ~/.chuzom/ (usage DB, .env, logs)"). Confirmed via
E2E that `~/.chuzom/agentic_models.json` survives a non-purge uninstall, as designed. This is
intentional, documented behavior, not a bug — noting only that the runtime `_run_uninstall()` print
output itself (as opposed to `--help`) does not repeat this disclosure at the point of action for a user
who never reads `--help`; this is a minor UX nicety, not a Critical/High/core-Medium honesty violation,
so it is not reported as a numbered finding.

## What else was checked (no findings)

- IDE-config templates (`_VSCODE_MCP_CONTENT`, `_WINDSURF_MCP_CONTENT`, `_CURSOR_RULE_CONTENT` in
  `install_hooks.py`, lines 1118-1179): current bundled content carries only qualified language ("routes
  to a cheaper capable model"); no unqualified claims present today. Noted as a soft, non-reportable
  observation: these have no drift/self-heal path (unlike hooks/rules), so a stale unqualified string
  from an old install could persist indefinitely on a real user's disk until explicit reinstall — but
  since current bundled content is clean, there's no live claim to point at.
  (An earlier IDE-config wording difference was found mid-audit as a *side effect of test setup*, not a
  product defect: running `install_hooks.main()`'s default install from the real repo's cwd regenerated
  `.windsurf/mcp.json` in-place. This was immediately caught via `git status --porcelain`, diffed, and
  reverted with `git checkout -- .windsurf/mcp.json`; confirmed no residual repo pollution.)
- `pyproject.toml` description, README hero (first 60 lines), and all shipped `.py`/`.md`/`.mdc` source
  under `src/chuzom/` and `skills/` — re-ran the existing `test_claims_no_fabricated_magnitudes.py` guard
  suite as-shipped (green) as a baseline before the carve-out abuse test above.
- `chuzom uninstall`'s primary hook/settings/MCP-registration cleanup — re-read in full; no gaps beyond
  the claw-code/IDE-config wiring already covered by RED2-6-02 (fixed on this path).

## Conclusion

Not CLEAN — 2 High findings, both fully CONFIRMED with reproducible, executed repro steps (no PLAUSIBLE
findings in this report). RED2-6-01 (Critical, prior iteration) is genuinely and thoroughly fixed —
tried hardest to break it via tampering with the exact security-relevant bytes it's supposed to protect,
and it held. RED2-6-02 (High, prior iteration) is fixed on its primary, README-documented path but
recurs unfixed in a sibling frozen public entry point that the tool itself directs users toward.
