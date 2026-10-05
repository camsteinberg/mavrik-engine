#!/bin/bash
# build.sh WORK [--release]
#
# Builds Wine and its Unix libraries from the pinned inputs, in the same steps on GitHub's Intel
# runner and on a Mac (Intel, or Apple silicon through Rosetta):
#   1. fetch.py      every input, checked against its pinned size and sha256, into WORK/downloads
#   2. toolchain     ccache from its pinned release into WORK/bin; bison 3, flex, pkg-config, cmake,
#                    and mingw-w64 gcc must be installed already (the workflow installs bison and
#                    mingw-w64 with Homebrew)
#   3. prepare.sh    the Wine sources, the addons.c check, the patches, the GStreamer packages
#   4. build-deps.sh our Unix libraries, into WORK/deps
#   5. build-wine.sh Wine, into WORK/wine-install
# Then assemble.sh, gates.sh and pack.sh make, check and pack the engine.
#
# Steps 4 and 5 leave WORK/<folder>/.stamp holding their cache key (buildinfo.py keys). A later run
# with the same key skips the step; FRESH=1 ignores the stamps. The workflow caches these folders
# under the same keys, so a restored cache is skipped the same way.
#
# Environment:
#   FETCH_ARGS  more arguments for fetch.py; on a Mac where curl is not used: "--via gh --from DIR"
#   JOBS        parallel make jobs (default: one and a half per CPU)
#   FRESH=1     rebuild every step
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
INPUTS="$REPO/inputs.json"
mkdir -p "$1"
WORK="$(cd "$1" && pwd)"
RELEASE=""
[ "${2:-}" = "--release" ] && RELEASE="--release"
S="$REPO/scripts"
ncpu="$(sysctl -n hw.ncpu)"

export MACOSX_DEPLOYMENT_TARGET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["engine"]["macos_deployment_target"])' "$INPUTS")"
export JOBS="${JOBS:-$(( ncpu + ncpu / 2 ))}"
export CCACHE_DIR="${CCACHE_DIR:-$WORK/ccache}" CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"
export CCACHE_COMPILERCHECK=content CCACHE_BASEDIR="$WORK" CCACHE_NOHASHDIR=1
export CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime
for d in /opt/homebrew/opt/bison/bin /usr/local/opt/bison/bin; do
    [ -x "$d/bison" ] && PATH="$d:$PATH" && break
done
export PATH="$WORK/bin:$PATH"

key() { python3 "$S/buildinfo.py" keys "$INPUTS" | sed -n "s/^$1=//p"; }
fresh() {  # fresh FOLDER KEY: true when FOLDER does not hold this recipe's finished step
    [ -n "${FRESH:-}" ] || [ ! -f "$1/.stamp" ] || [ "$(cat "$1/.stamp")" != "$2" ]
}

echo "::group::inputs"
echo "$INPUTS" > "$WORK/inputs.path"
# shellcheck disable=SC2086  # FETCH_ARGS is a list of words
python3 "$S/fetch.py" fetch "$INPUTS" "$WORK/downloads" $RELEASE ${FETCH_ARGS:-}
key downloads > "$WORK/downloads/.stamp"
echo "::endgroup::"

echo "::group::toolchain"
if [ "$(uname -m)" = arm64 ]; then
    arch -x86_64 /usr/bin/true || { echo "::error::Rosetta is needed: the engine's Unix side is x86_64"; exit 1; }
fi
ccache_archive="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["ccache"])' "$WORK/downloads/paths.json")"
ccache_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["inputs"]["ccache"]["version"])' "$INPUTS")"
if ! "$WORK/bin/ccache" --version 2>/dev/null | sed -n 1p | grep -q " $ccache_version\$"; then
    tmp="$(mktemp -d "$WORK/ccache-dist.XXXXXX")"
    tar -xzf "$ccache_archive" -C "$tmp"
    mkdir -p "$WORK/bin"
    cp "$(find "$tmp" -name ccache -type f -perm -u+x | sed -n 1p)" "$WORK/bin/ccache"
    rm -rf "$tmp"
fi
bison_major="$(bison --version | sed -n '1s/.* \([0-9][0-9]*\)\.[0-9.]*$/\1/p')"
[ "${bison_major:-0}" -ge 3 ] || { echo "::error::bison 3 or later is needed ($(command -v bison) is $(bison --version | sed -n 1p))"; exit 1; }
for tool in flex pkg-config cmake i686-w64-mingw32-gcc x86_64-w64-mingw32-gcc; do
    command -v "$tool" >/dev/null || { echo "::error::$tool is not installed"; exit 1; }
done
ccache --version | sed -n 1p
bison --version | sed -n 1p
flex --version
x86_64-w64-mingw32-gcc --version | sed -n 1p
i686-w64-mingw32-gcc --version | sed -n 1p
clang --version | sed -n 1p
cmake --version | sed -n 1p
echo "SDK $(xcrun --show-sdk-version), deployment target $MACOSX_DEPLOYMENT_TARGET, $(uname -m), make -j$JOBS"
sw_vers | paste -sd ' ' -
echo "::endgroup::"

bash "$S/prepare.sh" "$WORK/downloads/paths.json" "$INPUTS" "$WORK"

deps_key="$(key deps)"
if fresh "$WORK/deps" "$deps_key"; then
    echo "::group::our Unix libraries (gmp, nettle, gnutls, freetype, SDL2)"
    bash "$S/build-deps.sh" "$WORK/downloads/paths.json" "$WORK/deps-src" "$WORK/deps"
    echo "$deps_key" > "$WORK/deps/.stamp"
    echo "::endgroup::"
else
    echo "our Unix libraries: already built for $deps_key"
fi

wine_key="$(key wine)"
if fresh "$WORK/wine-install" "$wine_key"; then
    echo "::group::Wine (Unix x86_64, PE i386 and x86_64)"
    bash "$S/build-wine.sh" "$WORK" "$WORK/deps" "$(cat "$WORK/gst-root.path")"
    echo "$wine_key" > "$WORK/wine-install/.stamp"
    echo "::endgroup::"
else
    echo "Wine: already built for $wine_key"
fi
echo "build finished: $(du -sh "$WORK/wine-install" | cut -f1) in wine-install"
