#!/bin/bash
# assemble.sh WORK
#
# Makes the engine folder WORK/out/<name> from what build.sh left in WORK: the media notices
# (licences.py), the engine itself (assemble.py), its build record (buildinfo.py) and its licence
# folder (licences.py). Writes the name to WORK/out/name, and to GITHUB_OUTPUT when that is set.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
S="$REPO/scripts"
INPUTS="$(cat "$WORK/inputs.path")"

version="$(python3 "$S/buildinfo.py" keys "$INPUTS" | sed -n 's/^version=//p')"
wine_version="$(sed 's/^Wine version //' "$WORK/wine-src/VERSION")"
name="mavrik-engine-${wine_version}-${version}"
ENGINE="$WORK/out/$name"
mkdir -p "$WORK/out"
rm -rf "$ENGINE"

python3 "$S/licences.py" media-notices "$WORK"
python3 "$S/assemble.py" "$WORK" "$ENGINE"
python3 "$S/buildinfo.py" write "$INPUTS" "$WORK" "$ENGINE"
python3 "$S/licences.py" write "$WORK" "$ENGINE" "$REPO"

echo "$name" > "$WORK/out/name"
[ -z "${GITHUB_OUTPUT:-}" ] || echo "name=$name" >> "$GITHUB_OUTPUT"
du -sh "$ENGINE"
du -sh "$ENGINE"/* "$ENGINE"/lib/wine/* "$ENGINE"/share/wine/*
echo "engine: $ENGINE"
