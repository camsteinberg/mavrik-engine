#!/bin/bash
# gates.sh WORK
#
# Runs every gate on the engine assemble.sh made (gates.py run), then shows that each gate fails on
# a bad input (gates.py selftest). Results: WORK/gates/results.json and WORK/gates/selftest.json.
# Fails if any gate fails, or if any gate passes a bad input.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
ENGINE="$WORK/out/$(cat "$WORK/out/name")"

python3 "$REPO/scripts/gates.py" run "$ENGINE" "$WORK"
python3 "$REPO/scripts/gates.py" selftest "$ENGINE" "$WORK"
