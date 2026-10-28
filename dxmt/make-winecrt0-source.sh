#!/bin/bash
# make-winecrt0-source.sh REPO FILES OUT.tar.gz: the source of the Wine start-up code (winecrt0) DXMT's winemetal.dll
# carries, from 3Shain/wine at 4dd8a2d6dc (tag v8.16-3shain, Wine 8.16): the paths in FILES (closure.py: dlls/winecrt0
# and every header it includes) plus COPYING.LIB, LICENSE, AUTHORS and VERSION. git archive (mtime the commit's), one
# folder named after the commit, gzip -n: the same commit and list give the same bytes.
set -euo pipefail
repo=$1 files=$2 out=$3
C=4dd8a2d6dca39a116d0911f247bbaf1ad5e29471
# shellcheck disable=SC2046
git -C "$repo" archive --format=tar --prefix="wine-$C/" "$C" -- COPYING.LIB LICENSE AUTHORS VERSION $(cat "$files") | gzip -n -9 > "$out"
