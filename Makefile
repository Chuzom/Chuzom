.PHONY: verify lint test release bench bench-guard

# Gate every change: lint + tests + version-sync + routing report.
verify:
	@bash scripts/verify.sh

# Run the quality×cost benchmark (produces bench/results/<ts>.{json,md}).
# Needs local Ollama up; judge uses the Claude subscription. See bench/README.md.
bench:
	@uv run python -m bench

# CI gate: fail if routing quality regressed below floor OR results went stale.
# Run weekly in CI right after `make bench` (closes G-BENCH-1's staleness root).
bench-guard:
	@uv run python -m bench.guard

# Enforcement lint only — fail on direct provider calls bypassing Chuzom.
lint:
	@uv run python scripts/lint_no_direct_llm.py src/chuzom

# Full test suite.
test:
	@uv run --extra dev pytest -q

# Cut a release (bumps everything, tests, builds, tags, pushes, publishes).
# Usage: make release V=0.6.2   (add a CHANGELOG '## v0.6.2' section first)
release:
	@bash scripts/release.sh $(V)
