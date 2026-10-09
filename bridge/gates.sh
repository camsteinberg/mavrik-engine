#!/bin/bash
# bridge/gates.sh WORK
#
# Runs every bridge gate on the folder bridge/assemble.py made (bridgegates.py run), with the engine
# scripts/assemble.sh made in the same WORK, then shows each gate failing on a bad input
# (bridgegates.py selftest). Results: WORK/bridge/gates/results.json and selftest.json.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
BRIDGE="$WORK/bridge/out/$(cat "$WORK/bridge/out/name")"
. "$REPO/scripts/toolchain.sh" "$(cat "$WORK/inputs.path")"

python3 "$REPO/bridge/bridgegates.py" run "$BRIDGE" "$WORK"
python3 "$REPO/bridge/bridgegates.py" selftest "$BRIDGE" "$WORK"
