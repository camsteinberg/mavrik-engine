#!/bin/bash
# pack.sh WORK
#
# Packs the engine assemble.sh made into WORK/out/<name>.tar.xz with its .sha256, and puts the gate
# results, the build record and the learned pins beside it. The archive carries plain files and
# folders owned by root:wheel, with no extended attributes, ACLs or Mac metadata (macOS tags every
# downloaded or built file with com.apple.provenance; that stays on the build machine), and
# tarcheck.py checks it holds exactly the gated folder. XZ_THREADS limits xz's threads (default:
# one per CPU). Writes the name to GITHUB_OUTPUT and a line to GITHUB_STEP_SUMMARY when they are set.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
WORK="$(cd "$1" && pwd)"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
. "$REPO/scripts/toolchain.sh" "$(cat "$WORK/inputs.path")"
name="$(cat "$WORK/out/name")"
cd "$WORK/out"
rm -f "$name.tar.xz" "$name.tar.xz.sha256"
COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata --no-acls --no-fflags \
    --uid 0 --gid 0 --uname root --gname wheel \
    --options "xz:compression-level=9,xz:threads=${XZ_THREADS:-0}" -cJf "$name.tar.xz" "$name"
python3 "$REPO/scripts/tarcheck.py" "$name.tar.xz" "$name"
shasum -a 256 "$name.tar.xz" > "$name.tar.xz.sha256"
cp "$WORK/gates/results.json" "$name.gates.json"
cp "$WORK/gates/selftest.json" "$name.gates-selftest.json"
cp "$name/build-info.json" "$name.build-info.json"
cp "$WORK/downloads/learned-pins.json" "$name.learned-pins.json"
size="$(stat -f %z "$name.tar.xz")"
sha="$(cut -d' ' -f1 "$name.tar.xz.sha256")"
echo "$WORK/out/$name.tar.xz: $size bytes, sha256 $sha"
[ -z "${GITHUB_OUTPUT:-}" ] || echo "name=$name" >> "$GITHUB_OUTPUT"
[ -z "${GITHUB_STEP_SUMMARY:-}" ] || printf '### Engine\n\n- `%s.tar.xz`: %s bytes\n- sha256 `%s`\n' \
    "$name" "$size" "$sha" >> "$GITHUB_STEP_SUMMARY"
