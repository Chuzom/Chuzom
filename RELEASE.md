# Release Process

Complete guide for cutting a safe, reliable release without wasting GitHub Actions minutes.

## Quick Start

```bash
# 1. Run pre-release checklist (validates everything locally)
python scripts/pre-release-checklist.py

# 2. Fix any issues (auto-fix available for version mismatches)
python scripts/pre-release-checklist.py --auto-fix

# 3. Once checklist passes, run the actual release
python scripts/release.py 0.3.2
```

## The Release Checklist

**Before running `release.py`, always run the pre-release checklist:**

```bash
python scripts/pre-release-checklist.py
```

### What it checks

✅ **Git Status** — No uncommitted changes, correct branch (main/master/release)
✅ **Version Sync** — All plugin manifests match pyproject.toml
✅ **Changelog Entry** — Version exists in CHANGELOG.md
✅ **Debug Code** — No print(), TODO, FIXME, breakpoint() in source
✅ **Secrets** — No hardcoded API keys or tokens
✅ **Version Tests** — Runs the exact tests that GitHub will run

### Auto-fix version mismatches

If the checklist fails only on version sync, use auto-fix:

```bash
python scripts/pre-release-checklist.py --auto-fix
```

This automatically runs `sync-versions.py` and re-validates.

### Skip tests for local iteration

If you're iterating on pre-release changes, skip the slow test phase:

```bash
python scripts/pre-release-checklist.py --skip-tests
```

## The Release Script

Once the checklist passes, run the actual release:

```bash
python scripts/release.py 0.3.2
```

### What it does

1. Runs tests and linting
2. Bumps versions everywhere
3. Verifies changelog entry exists
4. Builds distribution artifacts (sdist + wheel)
5. Stages changes (git add)
6. Commits with message: `feat(v0.3.2): release`
7. Pushes to GitHub
8. Publishes to PyPI (requires PYPI_TOKEN env var)
9. Creates GitHub release with changelog
10. Reinstalls Codex plugin

### Options

```bash
# Dry run (print commands without executing)
python scripts/release.py 0.3.2 --dry-run

# Skip automated tests
python scripts/release.py 0.3.2 --skip-tests

# Skip PyPI publish (GitHub release only)
python scripts/release.py 0.3.2 --skip-publish

# Skip Codex plugin reinstall
python scripts/release.py 0.3.2 --skip-plugin-reinstall
```

## Post-Release Verification

After the release completes, GitHub Actions will run a full verification:

```bash
python scripts/verify-release.py
```

This checks:
- Package is available on PyPI
- Release exists on GitHub
- Full test suite passes

## Version Files

The version is managed in `pyproject.toml` as the source of truth:

```toml
[project]
version = "0.3.2"
```

The release process automatically syncs this to:
- `src/chuzom/__init__.py` (__version__)
- `.claude-plugin/plugin.json` (version field)
- `.claude-plugin/marketplace.json` (two locations)
- `.codex-plugin/plugin.json` (version field)
- `.codex-plugin/marketplace.json` (two locations)
- `.factory-plugin/plugin.json` (version field)
- `.factory-plugin/marketplace.json` (two locations)

**Never manually edit plugin version files.** Always let `sync-versions.py` manage them.

## Troubleshooting

### "Version mismatch detected!"

The pre-release checklist found version mismatches. Run:

```bash
python scripts/pre-release-checklist.py --auto-fix
```

Or manually fix and run:

```bash
python scripts/sync-versions.py
```

### "No changelog entry for v0.3.2"

Add a new section to `CHANGELOG.md` above any existing entries:

```markdown
## v0.3.2

### Features
- Feature description

### Fixes
- Fix description

### Internal
- Internal change description
```

Then run the checklist again.

### "pytest timed out"

The test suite sometimes hangs during async teardown. This is expected and harmless:

```
✅ Tests: All tests passed (Python shutdown hung after [100%];
  killed by 600s timeout — known asyncio teardown leak)
```

Proceed with the release if you see this (the checklist considers it a pass).

### "Uncommitted changes detected"

The pre-release checklist requires a clean working tree. Either:

```bash
# Commit your changes
git add -A
git commit -m "fix: some changes"

# OR stash them temporarily
git stash
```

### Release failed partway through

**Check the output carefully.** The release script does these in order:

1. Tests/lint ← If this fails, fix and re-run checklist
2. Version bump ← Pre-checklist should have caught this
3. Changelog ← Pre-checklist should have caught this
4. Build ← Should always succeed if tests passed
5. Git commit/push ← May fail if GitHub is down or auth issues
6. PyPI publish ← Requires PYPI_TOKEN env var set
7. GitHub release ← Requires gh CLI authenticated
8. Codex reinstall ← Optional, may fail if Codex not installed

If step 5+ fails, the package may be partially released. Check PyPI and GitHub manually, then decide whether to:
- Complete the remaining steps manually
- Create a hotfix release on top

## Why Pre-Release Matters

Every GitHub Actions minute costs money and takes time. The pre-release checklist:

- **Catches version mismatches locally** (the most common failure)
- **Runs tests before wasting CI minutes** (syntax errors, type issues)
- **Validates changelog** (prevents incomplete release notes)
- **Detects debug code** (prevents debug statements in production)
- **Checks for hardcoded secrets** (basic defense-in-depth)

This single step typically saves 5-10 failed release attempts per quarter, preventing wasted CI resources and release delays.

## Emergency: Force a Release (last resort)

If something goes wrong mid-release and you need to manually complete it:

```bash
# Check what actually got released
pip install --upgrade chuzom-router
pip show chuzom-router | grep Version

# Check GitHub
gh release view --repo ypollak2/chuzom

# If both are behind where you want, increment version and try again
# If one succeeded but not the other, complete manually:
# - Missing PyPI push? Run: uv publish --token <PYPI_TOKEN>
# - Missing GitHub release? Run: gh release create v0.3.2 --notes "..."
```

**Then document what went wrong** so it can be prevented next time.
