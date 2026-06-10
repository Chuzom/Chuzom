# Contributing to Chuzom

Thanks for your interest in Chuzom — a local-first LLM router for developer
workstations. This guide gets you from clone to merged PR.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## TL;DR

```bash
git clone https://github.com/ypollak2/chuzom
cd chuzom
uv sync --extra dev            # install runtime + dev/test deps
uv run pytest -q               # run the fast test suite
uvx ruff check src/ tests/     # lint
```

Then branch, write a failing test, make it pass, and open a PR.

---

## Local development

Chuzom targets **Python 3.10+** and uses [uv](https://docs.astral.sh/uv/) for
environment + dependency management.

```bash
uv sync --extra dev            # core + pytest, pytest-cov, ruff, etc.
uv run chuzom doctor           # sanity-check your local install
```

Optional extras (install only what you touch):

| Extra | Pulls in | Use when |
|---|---|---|
| `semantic` | sentence-transformers, sqlite-vec | working on the semantic cache |
| `tracing` | opentelemetry-sdk + OTLP exporter | working on observability |
| `postgres` | psycopg | working on the multi-instance budget backend |
| `code-context` | tree-sitter | working on code-context extraction |

```bash
uv sync --extra dev --extra tracing
```

---

## Tests

We follow a test-first workflow. **Write a failing test that reproduces the bug
or specifies the feature, then make it pass.**

```bash
uv run pytest -q                       # fast suite (CI default markers)
uv run pytest tests/qa/                # a single area
uv run pytest tests/test_router.py -q  # a single file
uv run pytest --cov=src/chuzom --cov-report=term-missing
```

The default marker set skips `slow`, `requires_ollama`, and `requires_api_keys`
(see `addopts` in `pyproject.toml`). CI runs the same default sweep on Python
3.11 and 3.13.

Guidelines:

- New behavior needs tests. Bug fixes start with a failing regression test.
- Name tests `test_<what>_<condition>_<expected>`.
- Keep tests isolated — no reliance on `~/.chuzom` state or network. Use the
  fixtures in `tests/conftest.py` and temp paths via `CHUZOM_*_PATH` env vars.

---

## Code style

- **Lint:** `uvx ruff check src/ tests/` must be clean (line length 100).
- **Type hints** on all public function signatures; prefer `X | None` over
  `Optional[X]` (3.10+).
- **Immutability** — return new objects, don't mutate in place. Prefer
  `@dataclass(frozen=True)` for value objects.
- **Small, focused modules.** New files beat growing the existing god-modules
  (`router.py`, `cost.py`, `tools/admin.py`); aim for < 800 lines.
- **Errors:** throw at boundaries, catch at entry points. No bare
  `except Exception: pass` — log with context or re-raise.
- **No secrets in code or tests.** Provider keys come from env vars only.

---

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`,
`ci`, `revert`. Example: `fix(router): release budget reservation on cancel`.

Keep one concern per PR.

---

## Pull requests

1. Branch from `main`: `git checkout -b fix/short-description`.
2. Make your change with tests; keep the diff focused.
3. Run `uv run pytest -q` and `uvx ruff check src/ tests/` locally.
4. Bump the version + `CHANGELOG.md` only if asked — maintainers handle releases.
5. Fill in the PR template checklist. CI (tests + lint + security scans) must be
   green.

A maintainer will review. Address review comments by pushing follow-up commits
(we squash on merge).

---

## Package-distribution safety (important)

Chuzom ships to PyPI. **Never** add internal docs, secrets, dev dirs, or local
venvs to the published sdist. The allowlist/exclude rules live in
`[tool.hatch.build.targets.sdist]` in `pyproject.toml`. After any packaging
change, run:

```bash
uv build
tar tzf dist/*.tar.gz | grep -v /src/   # confirm only intended files survive
```

No `.env`, no `CLAUDE.md`, no `tests/`, no `.venv*` in the tarball — ever.

---

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/ypollak2/chuzom/issues/new/choose).
For **security vulnerabilities**, do **not** open a public issue — follow the
private disclosure process in [SECURITY.md](SECURITY.md).

---

## Questions

Open a [discussion or issue](https://github.com/ypollak2/chuzom/issues). We aim
to respond within a couple of working days.
