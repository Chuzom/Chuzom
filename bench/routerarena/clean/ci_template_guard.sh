#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# ci_template_guard.sh — structural firewall against RouterArena-template fitting.
#
# Every prior Chuzom RA submission (legacy v0.5.2 AND PR #158 Gate-2) was
# rejected/withdrawn for keying routing on RouterArena's injected prompt
# TEMPLATES — strings that only appear because you inspected RA's eval prompts.
# This guard greps the shipped router source for those literals and FAILS the
# build if any appear.
#
# Usage: bash bench/routerarena/clean/ci_template_guard.sh [--strict]
set -euo pipefail

STRICT=0
for a in "$@"; do [[ "$a" == "--strict" ]] && STRICT=1; done

ROUTER_SRC=(
    "bench/routerarena/clean/router_core.py"
    "bench/routerarena/clean/chuzom_clean_router.py"
    # Production classification path (semantic classifier + reason-gate + the
    # offline generator/audit). These inform routing parameters, so they are
    # held to the same no-RA-template rule as the submission router.
    "src/chuzom/semantic_classify.py"
    "src/chuzom/reason_gate.py"
    "src/chuzom/semantic_centroids.py"
    "src/chuzom/contamination_audit.py"
    "scripts/gen_semantic_corpus.py"
    "scripts/build_semantic_centroids.py"
)
BANNED=(
    'Context:[[:space:]]*None'
    '\\boxed'
    'Please solve the following mathematical problem'
    'Please read the following context and answer the question'
    'Please read the following question and provide the correct answer'
    'Please read the following multiple-choice'
    'Natural Language Inference'
    'Premise.*Hypothesis'
    '`1` for correct'
    'for correct, `0` for incorrect'
    '"moves":'
    'This is the clue:'
    'Generate an executable Python function'
    'Does the word have the same meaning in both sentences'
)

echo "=== RouterArena clean-router template guard ==="
violations=0
for f in "${ROUTER_SRC[@]}"; do
    [[ -f "$f" ]] || { echo "  (skip, not present yet: $f)"; continue; }
    for pat in "${BANNED[@]}"; do
        if grep -nE "$pat" "$f" >/dev/null 2>&1; then
            echo "VIOLATION: RA-template literal /$pat/ found in $f:"
            grep -nE "$pat" "$f" | sed 's/^/    /'
            violations=$((violations+1))
        fi
    done
done

echo ""
if [[ $violations -eq 0 ]]; then
    echo "✓ No RouterArena-template literals in shipped router source."
    exit 0
else
    echo "✗ $violations template-literal violation(s) — router is fitting to RA structure."
    [[ $STRICT -eq 1 ]] && exit 1
    echo "  (run with --strict to fail the build)"
    exit 0
fi
