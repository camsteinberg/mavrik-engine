#!/bin/bash
# bridge/assemble.sh WORK
#
# Makes the bridge's folder WORK/bridge/out/<name> from what bridge/build.sh left in WORK/bridge/install
# (bridge/assemble.py: the files, NOTICE.txt, build-info.json and licences/).
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
. "$REPO/scripts/toolchain.sh" "$(cat "$WORK/inputs.path")"
python3 "$REPO/bridge/assemble.py" "$WORK"
