#!/bin/bash
# make-source.sh SRC COMMIT OUT.tar.gz: DXMT at COMMIT with its two submodules filled at the commits COMMIT records for
# them, from git objects only (no working tree, no .git), one top folder named dxmt-<full commit>; gzip -n, so the same
# commits give the same bytes. SRC is a clone with its submodules fetched (git submodule update --init).
set -euo pipefail
src=$1 commit=$2 out=$3
C=$(git -C "$src" rev-parse --verify "$commit^{commit}") N=dxmt-$C
sub() { git -C "$src" ls-tree "$C" "$1" | awk '$2 == "commit" {print $3}'; }
nvapi=$(sub external/nvapi) directx=$(sub include/native/directx)
[ -n "$nvapi" ] && [ -n "$directx" ] || { echo "$C does not record both submodules" >&2; exit 1; }
t=$(mktemp -d); trap 'rm -r "$t"' EXIT
git -C "$src" archive --format=tar --prefix="$N/" "$C" > "$t/main.tar"
git -C "$src/external/nvapi" archive --format=tar --prefix="$N/external/nvapi/" "$nvapi" > "$t/nvapi.tar"
git -C "$src/include/native/directx" archive --format=tar --prefix="$N/include/native/directx/" "$directx" > "$t/directx.tar"
( cd "$t" && /usr/bin/tar -cf all.tar --format ustar @main.tar @nvapi.tar @directx.tar )
gzip -n -9 < "$t/all.tar" > "$out"
echo "$out: DXMT $C, external/nvapi $nvapi, include/native/directx $directx"
