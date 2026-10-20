#!/bin/bash
# bridge/pack.sh WORK
#
# Packs the bridge folder into WORK/bridge/out/<name>.tar.xz with its .sha256, as scripts/pack.sh packs
# the engine: plain files and folders owned by root:wheel, no Mac metadata, checked by tarcheck.py
# against the gated folder. The gate results and the build record go beside it. It refuses unless
# bridge/gates.sh ran on this folder after it was assembled and every gate and self-test row passed.
# Nothing here publishes anything.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
WORK="$(cd "$1" && pwd)"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
. "$REPO/scripts/toolchain.sh" "$(cat "$WORK/inputs.path")"
name="$(cat "$WORK/bridge/out/name")"
cd "$WORK/bridge/out"
python3 - "$WORK/bridge/gates" "$name/build-info.json" <<'EOF'
import json, os, sys
gates, info = sys.argv[1], sys.argv[2]
for f in ("results.json", "selftest.json"):
    path = os.path.join(gates, f)
    if not os.path.isfile(path):
        sys.exit(f"::error::no {f}: run bridge/gates.sh first")
    if os.path.getmtime(path) <= os.path.getmtime(info):
        sys.exit(f"::error::{f} is older than {info}: run bridge/gates.sh on this folder first")
    rows = json.load(open(path))
    failed = [r.get("gate", "?") for r in rows if r.get("result") != "PASS"]
    if not rows or failed:
        sys.exit(f"::error::{f}: not every row passed ({', '.join(failed) or 'no rows'})")
print("gate results: every row passed, after the folder was assembled")
EOF
rm -f "$name.tar.xz" "$name.tar.xz.sha256"
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata --no-acls --no-fflags \
    --uid 0 --gid 0 --uname root --gname wheel \
    --options "xz:compression-level=9,xz:threads=${XZ_THREADS:-0}" -cJf "$name.tar.xz" "$name"
python3 "$REPO/scripts/tarcheck.py" "$name.tar.xz" "$name"
shasum -a 256 "$name.tar.xz" > "$name.tar.xz.sha256"
cp "$WORK/bridge/gates/results.json" "$name.gates.json"
cp "$WORK/bridge/gates/selftest.json" "$name.gates-selftest.json"
cp "$name/build-info.json" "$name.build-info.json"
cp "$WORK/bridge/downloads/learned-pins.json" "$name.learned-pins.json"
echo "$WORK/bridge/out/$name.tar.xz: $(stat -f %z "$name.tar.xz") bytes, sha256 $(cut -d' ' -f1 "$name.tar.xz.sha256")"
