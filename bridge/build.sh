#!/bin/bash
# bridge/build.sh WORK [--release]
#
# Builds Valve's Steam bridge for the engine that scripts/build.sh built in WORK: lsteamclient (its
# i386 and x86_64 Windows halves and its x86_64 Unix half) and the steam.exe stub, from Valve's Proton
# source at the commit bridge/inputs.json pins, with the patches in bridge/patches/. The way Proton,
# NotProton and an earlier test build with Spacewar built them: as Wine modules, by Wine's own make,
# against the engine's own Wine tree. Run it after scripts/build.sh. The engine's tree and Wine are only
# read; the compiles share the engine's ccache in WORK/ccache, and add to it.
#   1. fetch.py     Proton's tarball, checked against its pins, into WORK/bridge/downloads
#   2. proton.py    lsteamclient/, steam_helper/ and Valve's two licence files, checked against the
#                   pinned tree digest, into WORK/bridge/proton
#   3. the tree     an APFS clone of the engine's patched WORK/wine-src as WORK/bridge/wine-src, with
#                   dlls/lsteamclient and programs/steam added and bridge/patches/*.patch applied
#   4. configure    exactly as scripts/build-wine.sh does; config.h and the configure command line
#                   (from config.log, without the source folder) must equal the engine's
#   5. make         only dlls/lsteamclient/all and programs/steam/all, and what they need (Wine's
#                   tools, headers, import libraries, ntdll.so to link against), as x86_64
#   6. the files    into WORK/bridge/install/lib/wine/<arch>/, laid out as in the engine
# WORK/bridge/wine-src and WORK/bridge/wine-build are removed when the build succeeds; ccache keeps a
# repeat fast. WORK/bridge/install/.stamp holds the cache key, and a later run with the same key
# skips steps 3 to 6 (FRESH=1 ignores it).
#
# Environment: FETCH_ARGS, JOBS and FRESH, as for scripts/build.sh.
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
S="$REPO/scripts" B="$REPO/bridge"
INPUTS="$B/inputs.json"
WORK="$(cd "$1" && pwd)"
BW="$WORK/bridge"
RELEASE=""
[ "${2:-}" = "--release" ] && RELEASE="--release"
ncpu="$(sysctl -n hw.ncpu)"
. "$S/toolchain.sh" "$(cat "$WORK/inputs.path")"

# The engine this bridge is built against must be the one this recipe makes.
wine_key="$(python3 "$S/buildinfo.py" keys "$(cat "$WORK/inputs.path")" | sed -n 's/^wine=//p')"
[ -f "$WORK/wine-install/.stamp" ] && [ "$(cat "$WORK/wine-install/.stamp")" = "$wine_key" ] \
    || { echo "::error::WORK/wine-install is not this recipe's Wine ($wine_key): run scripts/build.sh first"; exit 1; }
[ -f "$WORK/wine-src/VERSION" ] || { echo "::error::no WORK/wine-src: run scripts/build.sh first"; exit 1; }

export MACOSX_DEPLOYMENT_TARGET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["engine"]["macos_deployment_target"])' "$(cat "$WORK/inputs.path")")"
export JOBS="${JOBS:-$(( ncpu + ncpu / 2 ))}"
export CCACHE_DIR="${CCACHE_DIR:-$WORK/ccache}" CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"
export CCACHE_COMPILERCHECK=content CCACHE_BASEDIR="$WORK" CCACHE_NOHASHDIR=1
export CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime
export PATH="$WORK/bin:$PATH"
x86() { arch -x86_64 "$@"; }
MAP="-ffile-prefix-map=$WORK/="

echo "::group::bridge inputs"
mkdir -p "$BW"
# shellcheck disable=SC2086  # FETCH_ARGS is a list of words
python3 "$S/fetch.py" fetch "$INPUTS" "$BW/downloads" $RELEASE ${FETCH_ARGS:-}
rm -rf "$BW/proton" "$BW/proton.part"
python3 "$B/proton.py" unpack "$INPUTS" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["proton-source"])' "$BW/downloads/paths.json")" "$BW/proton"
echo "::endgroup::"

key="bridge-$(python3 - "$B" "$wine_key" <<'EOF'
import hashlib, os, sys
b, wine_key = sys.argv[1], sys.argv[2]
h = hashlib.sha256(wine_key.encode())
for name in ["inputs.json", "build.sh"] + sorted("patches/" + p for p in os.listdir(os.path.join(b, "patches"))):
    h.update(name.encode() + open(os.path.join(b, name), "rb").read())
print(h.hexdigest()[:20])
EOF
)"
if [ -z "${FRESH:-}" ] && [ -f "$BW/install/.stamp" ] && [ "$(cat "$BW/install/.stamp")" = "$key" ]; then
    echo "Steam bridge: already built for $key"
    exit 0
fi

echo "::group::the tree"
SRC="$BW/wine-src" BUILD="$BW/wine-build" DEST="$BW/install"
rm -rf "$SRC" "$BUILD" "$DEST"
cp -c -R "$WORK/wine-src" "$SRC" 2>/dev/null || { rm -rf "$SRC"; cp -R "$WORK/wine-src" "$SRC"; }
cp -R "$BW/proton/lsteamclient" "$SRC/dlls/lsteamclient"
mkdir "$SRC/programs/steam"
cp "$BW/proton/steam_helper/steam.c" "$BW/proton/steam_helper/Makefile.in" "$SRC/programs/steam/"
cd "$SRC"
for p in "$B"/patches/*.patch; do
    echo "applying bridge/patches/$(basename "$p")"
    patch -p1 --forward --batch --fuzz=0 --no-backup-if-mismatch < "$p" \
        || { echo "::error::bridge/patches/$(basename "$p") does not apply cleanly"; exit 1; }
done
rejects="$(find . -name '*.rej' -o -name '*.orig' | sed -n "1,5p")"
[ -z "$rejects" ] || { echo "::error::patch leftovers: $rejects"; exit 1; }
cd "$WORK"
echo "::endgroup::"

echo "::group::configure (as scripts/build-wine.sh)"
export PKG_CONFIG_PATH="$WORK/deps/lib/pkgconfig:$(cat "$WORK/gst-root.path")/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH"
# The engine's 32-bit flags (patch 0038's recipe line), read from build-wine.sh so the two never drift.
I386_EXTRA="$(sed -n 's/^I386_EXTRA="\(.*\)"$/\1/p' "$REPO/scripts/build-wine.sh")"
[ -n "$I386_EXTRA" ] || { echo "::error::no I386_EXTRA in scripts/build-wine.sh"; exit 1; }
mkdir -p "$BUILD"
cd "$BUILD"
x86 "$SRC/configure" \
    --prefix=/opt/mavrik-engine \
    --enable-archs=i386,x86_64 \
    --disable-tests \
    --with-mingw \
    --with-coreaudio --with-ffmpeg --with-freetype --with-gnutls --with-gstreamer \
    --with-pthread --with-sdl --with-vulkan \
    --without-alsa --without-capi --without-cups --without-dbus --without-fontconfig \
    --without-gettextpo --without-gphoto --without-gssapi --without-hwloc --without-inotify \
    --without-krb5 --without-netapi --without-oss --without-pcap --without-pcsclite \
    --without-pulse --without-sane --without-udev --without-usb --without-v4l2 \
    --without-wayland --without-x \
    CC="ccache clang -arch x86_64" CXX="ccache clang++ -arch x86_64" \
    CFLAGS="-O2 $MAP" CROSSCFLAGS="-O2 $MAP" i386_CFLAGS="-O2 $MAP $I386_EXTRA" \
    LDFLAGS="-Wl,-headerpad_max_install_names" \
    i386_CC="ccache i686-w64-mingw32-gcc" x86_64_CC="ccache x86_64-w64-mingw32-gcc" \
    ac_cv_lib_soname_vulkan= ac_cv_lib_soname_MoltenVK=libMoltenVK.dylib \
    > configure.log 2>&1 || { tail -200 config.log; exit 1; }
# The bridge must be built against the very Wine the engine is: the same configuration, to the line.
if ! cmp -s include/config.h "$WORK/wine-install/.build/config.h"; then
    diff "$WORK/wine-install/.build/config.h" include/config.h | sed -n '1,40p'
    echo "::error::configure gave the bridge another config.h than the engine's"; exit 1
fi
# config.h does not show every setting (CFLAGS, LDFLAGS, CC), so the command line must match too.
cmdline() { sed -n 's|^  \$ .*/configure |configure |p' "$1" | sed -n 1p; }
engine_cmd="$(cmdline "$WORK/wine-install/.build/config.log")"
[ -n "$engine_cmd" ] || { echo "::error::no configure command line in the engine's config.log"; exit 1; }
if [ "$(cmdline config.log)" != "$engine_cmd" ]; then
    diff <(echo "$engine_cmd" | tr ' ' '\n') <(cmdline config.log | tr ' ' '\n') | sed -n '1,40p'
    echo "::error::configure ran with other settings than the engine's"; exit 1
fi
echo "config.h and the configure command line are the engine's"
echo "::endgroup::"

echo "::group::make (lsteamclient and steam.exe only)"
ccache -z >/dev/null || true
x86 make -j"$JOBS" dlls/lsteamclient/all programs/steam/all
ccache -s || true
echo "::endgroup::"

echo "::group::the files"
for f in "dlls/lsteamclient/i386-windows/lsteamclient.dll lib/wine/i386-windows/lsteamclient.dll" \
         "dlls/lsteamclient/x86_64-windows/lsteamclient.dll lib/wine/x86_64-windows/lsteamclient.dll" \
         "dlls/lsteamclient/lsteamclient.so lib/wine/x86_64-unix/lsteamclient.so" \
         "programs/steam/i386-windows/steam.exe lib/wine/i386-windows/steam.exe" \
         "programs/steam/x86_64-windows/steam.exe lib/wine/x86_64-windows/steam.exe"; do
    set -- $f
    [ -f "$1" ] || { echo "::error::make did not build $1"; exit 1; }
    mkdir -p "$DEST/$(dirname "$2")"
    cp "$1" "$DEST/$2"
    echo "$2: $(stat -f %z "$DEST/$2") bytes"
done
mkdir -p "$DEST/.build"
cp include/config.h config.log "$DEST/.build/"
python3 "$S/buildinfo.py" toolchain > "$DEST/.build/toolchain.json"
echo "::endgroup::"

cd "$WORK"
rm -rf "$BUILD" "$SRC"
echo "$key" > "$DEST/.stamp"
echo "Steam bridge built for $key"
