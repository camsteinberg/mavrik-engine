#!/bin/bash
# build-wine.sh WORK DEPS GST_ROOT
#
# Configures and builds Wine from WORK/wine-src (already patched) in WORK/wine-build, and
# installs the run-time files (make install-lib) into WORK/wine-install. WORK/wine-build is removed
# once the install is done.
#   Unix side: x86_64, clang. The tree's Metal layer is x86_64 only. configure and make run as
#              x86_64 (through Rosetta on Apple silicon), so the build is the same as on an Intel Mac.
#   PE side:   i386 and x86_64 with mingw-w64 gcc (llvm-mingw is known to break Steam's login).
# Libraries come only from DEPS (our own builds) and the expanded GStreamer packages; the
# build stops if FFmpeg, GStreamer, FreeType, GnuTLS, SDL2 or Vulkan (MoltenVK) went missing,
# because configure only warns about those and would build a quietly smaller Wine.
# JOBS sets make's parallel jobs.
set -euo pipefail

WORK="$1" DEPS="$2" GST="$3"
SRC="$WORK/wine-src" BUILD="$WORK/wine-build" DEST="$WORK/wine-install"
: "${MACOSX_DEPLOYMENT_TARGET:?set MACOSX_DEPLOYMENT_TARGET}"
ncpu=$(sysctl -n hw.ncpu)
JOBS="${JOBS:-$(( ncpu + ncpu / 2 ))}"
x86() { arch -x86_64 "$@"; }

export PKG_CONFIG_PATH="$DEPS/lib/pkgconfig:$GST/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PKG_CONFIG_PATH"
pkg-config --modversion freetype2 gnutls sdl2 gstreamer-1.0 libavcodec | paste -sd ' ' -

rm -rf "$BUILD" "$DEST"
mkdir -p "$BUILD"
cd "$BUILD"

# --with-opengl is left out on purpose: asked for explicitly, configure makes the missing EGL
# headers an error (macOS has none); left alone, the Mac driver links OpenGL.framework.
# MoltenVK is named by its file name only (ac_cv_lib_soname_MoltenVK): the engine carries its
# own copy and Wine opens it by that name from the engine's lib folder.
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
    CFLAGS="-O2" CROSSCFLAGS="-O2" LDFLAGS="-Wl,-headerpad_max_install_names" \
    i386_CC="ccache i686-w64-mingw32-gcc" x86_64_CC="ccache x86_64-w64-mingw32-gcc" \
    ac_cv_lib_soname_vulkan= ac_cv_lib_soname_MoltenVK=libMoltenVK.dylib \
    || { tail -200 config.log; exit 1; }

need() {  # need NAME TEST-DESCRIPTION COMMAND...
    local name="$1"; shift
    if ! "$@" >/dev/null 2>&1; then echo "::error::configure left out $name"; exit 1; fi
    echo "configure found $name"
}
need FFmpeg        grep -q '^#define HAVE_FFMPEG 1' include/config.h
need GStreamer     grep -qE '^GSTREAMER_LIBS *= *.+' Makefile
need FreeType      grep -q '^#define SONAME_LIBFREETYPE ' include/config.h
need GnuTLS        grep -q '^#define SONAME_LIBGNUTLS ' include/config.h
need SDL2          grep -q '^#define SONAME_LIBSDL2 ' include/config.h
need Vulkan        grep -q '^#define SONAME_LIBVULKAN "libMoltenVK.dylib"' include/config.h
grep '^#define SONAME_' include/config.h

ccache -z >/dev/null || true
x86 make -j"$JOBS"
x86 make -j"$JOBS" install-lib DESTDIR="$DEST"
ccache -s || true

# What later steps need from the build tree (and config.log, for the record). Then the tree goes:
# every build starts from an empty one (ccache keeps that fast), so its objects are never used again.
mkdir -p "$DEST/.build"
cp include/config.h Makefile config.log "$DEST/.build/"
echo "installed:"
find "$DEST" -maxdepth 4 -type d | sed "s|$DEST/||" | sort | sed -n "1,30p"
cd "$WORK"
rm -rf "$BUILD"
