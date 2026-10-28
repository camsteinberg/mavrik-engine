#!/bin/bash
# make-source.sh SRC OUT.tar.gz: DXMT at a148782d43 with its two submodules filled, from git objects only (no working
# tree, no .git), one top folder named after the commit; gzip -n, so the same commits give the same bytes.
set -euo pipefail
src=$1 out=$2
C=a148782d431249405acdb1531dbb0c7e737bbece N=dxmt-$C
t=$(mktemp -d); trap 'rm -r "$t"' EXIT
git -C "$src" archive --format=tar --prefix="$N/" "$C" > "$t/main.tar"
git -C "$src/external/nvapi" archive --format=tar --prefix="$N/external/nvapi/" d08488fcc82eef313b0464db37d2955709691e94 > "$t/nvapi.tar"
git -C "$src/include/native/directx" archive --format=tar --prefix="$N/include/native/directx/" 9df86f2341616ef1888ae59919feaa6d4fad693d > "$t/directx.tar"
( cd "$t" && /usr/bin/tar -cf all.tar --format ustar @main.tar @nvapi.tar @directx.tar )
gzip -n -9 < "$t/all.tar" > "$out"
