#!/usr/bin/env bash
# Runs every project's test suite.
#
# Each project is self-contained: its package lives at the project root, so the
# tests must run from inside that directory. Running pytest from the repo root
# fails to import them, which is why this script exists.
set -uo pipefail

cd "$(dirname "$0")/projects"

total=0
failed=0

for project in p0*/; do
    printf '%-24s' "${project%/}"
    output=$(cd "$project" && python3 -m pytest -q 2>&1 | tail -1)
    echo "$output"

    if [[ "$output" == *"passed"* && "$output" != *"failed"* ]]; then
        count=$(echo "$output" | grep -oE '^[0-9]+')
        total=$((total + count))
    else
        failed=$((failed + 1))
    fi
done

echo
if [[ $failed -eq 0 ]]; then
    echo "All suites green: $total tests passed."
else
    echo "$failed suite(s) failed."
    exit 1
fi
