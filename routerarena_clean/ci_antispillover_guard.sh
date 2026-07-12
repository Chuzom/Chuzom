#!/usr/bin/env bash
# ci_antispillover_guard.sh — fail if any router/parameter code reads a RA
# evaluation output (per-dataset results, RA gold/labels, quarantine dir).
# Eval outputs are RA-accuracy data; letting them inform a router parameter is
# the PR-#155 violation. Analysis code under routerarena_clean/sandbox is
# intentionally NOT scanned (it evaluates; it does not feed the router).
set -euo pipefail
echo "=== RA eval-output spillover guard ==="
PATTERNS=('_sub10_result\.json' 'routerarena_clean/quarantine' 'sub10_labels\.json' 'full_labels\.json' 'chuzom-v3-pred\.json')
SCAN=(src/chuzom routerarena_submission/router)
v=0
for d in "${SCAN[@]}"; do
  [ -d "$d" ] || continue
  for p in "${PATTERNS[@]}"; do
    if grep -rnE "$p" "$d" --include=*.py >/dev/null 2>&1; then
      echo "VIOLATION: /$p/ referenced by router/param code in $d:"
      grep -rnE "$p" "$d" --include=*.py | sed 's/^/    /'
      v=$((v+1))
    fi
  done
done
if [ "$v" -eq 0 ]; then echo "OK — no router/param code reads RA eval outputs."; exit 0
else echo "FAIL — $v spillover reference(s); RA eval data must not inform routing."; exit 1; fi
