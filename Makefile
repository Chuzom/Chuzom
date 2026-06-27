.PHONY: verify lint test release

# Gate every change: lint + tests + version-sync + routing report.
verify:
	@bash scripts/verify.sh

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
