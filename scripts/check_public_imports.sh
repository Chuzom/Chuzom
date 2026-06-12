#!/bin/bash
# PUBLIC-ONLY BUILD CHECK: Verify no enterprise imports leak into public code
# This script runs in CI to ensure the public distribution is truly enterprise-free

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Checking for forbidden enterprise imports in public code ==="

# Check public source code for any imports of chuzom.enterprise
echo "Scanning src/chuzom (excluding enterprise/)..."
if grep -r "from chuzom.enterprise\|import chuzom.enterprise" \
    "$REPO_ROOT/src/chuzom" \
    --include="*.py" \
    --exclude-dir="enterprise" 2>/dev/null; then
    echo "❌ ERROR: Found forbidden enterprise imports in public code!"
    exit 1
else
    echo "✓ No forbidden imports found in src/chuzom"
fi

# Check that core routing/redaction/quotas modules don't import enterprise
echo "Checking critical public modules..."
for module in redaction_routing.py quota_routing.py audit_routing.py router.py; do
    echo "  - $module"
    if grep "from chuzom.enterprise\|import chuzom.enterprise" "$REPO_ROOT/src/chuzom/$module" 2>/dev/null; then
        echo "❌ ERROR: $module imports from enterprise!"
        exit 1
    fi
done

echo ""
echo "✓ All checks passed. Public code is enterprise-free."
exit 0
