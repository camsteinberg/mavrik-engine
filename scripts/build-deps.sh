#!/bin/bash
# build-deps.sh PATHS_JSON WORK PREFIX
#
# Builds the Unix libraries Wine loads at run time from their pinned source tarballs
# (inputs.json): gmp, nettle, gnutls, freetype and SDL2, for x86_64, into PREFIX.
# Each is built with the fewest options that still give Wine what it uses, so the
# engine carries as few extra libraries as it can:
#   gnutls  - with its own copies of libtasn1 and libunistring, no p11-kit, no IDN,
#             no compression, no gettext. Wine uses it for TLS and its crypto calls.
#   freetype - no harfbuzz, png or brotli; zlib and bzip2 come from macOS.
#   gmp and nettle - "fat" builds that pick their CPU code at run time, so one build is
#             safe on every Intel Mac and under Rosetta.
set -euo pipefail

PATHS="$1" WORK="$2" PREFIX="$3"
mkdir -p "$WORK" "$PREFIX"
: "${MACOSX_DEPLOYMENT_TARGET:?set MACOSX_DEPLOYMENT_TARGET}"
JOBS=$(( $(sysctl -n hw.ncpu) + 1 ))

src() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PATHS" "$1"; }
unpack() {  # unpack KEY -> echoes the source folder
    local archive dir
    archive="$(src "$1")"
    dir="$WORK/$1"
    rm -rf "$dir" && mkdir -p "$dir"
    tar -xf "$archive" -C "$dir"
    find "$dir" -mindepth 1 -maxdepth 1 -type d | head -1
}

export CC="ccache clang" CXX="ccache clang++"
export CFLAGS="-O2 -arch x86_64" CXXFLAGS="-O2 -arch x86_64"
export CPPFLAGS="-I$PREFIX/include"
export LDFLAGS="-L$PREFIX/lib -Wl,-headerpad_max_install_names"
# Only our own .pc files: nothing from Homebrew on the runner may be found by accident.
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"

common=(--prefix="$PREFIX" --enable-shared --disable-static)

echo "::group::gmp"
d="$(unpack gmp)"
( cd "$d" && ./configure "${common[@]}" --enable-fat --disable-cxx && make -j"$JOBS" && make install )
echo "::endgroup::"

echo "::group::nettle"
d="$(unpack nettle)"
( cd "$d" && ./configure "${common[@]}" --enable-fat --disable-documentation --disable-openssl \
    && make -j"$JOBS" && make install )
echo "::endgroup::"

echo "::group::gnutls"
d="$(unpack gnutls)"
( cd "$d" && ./configure "${common[@]}" \
    --disable-doc --disable-manpages --disable-tests --disable-full-test-suite --disable-tools \
    --disable-cxx --disable-guile --disable-nls --disable-libdane \
    --with-included-libtasn1 --with-included-unistring \
    --without-p11-kit --without-idn --without-tpm --without-tpm2 \
    --without-brotli --without-zstd --without-zlib --without-leancrypto \
    && make -j"$JOBS" && make install )
echo "::endgroup::"

echo "::group::freetype"
d="$(unpack freetype)"
( cd "$d" && ./configure "${common[@]}" --without-harfbuzz --without-png --without-brotli \
    --with-zlib=yes --with-bzip2=yes && make -j"$JOBS" && make install )
echo "::endgroup::"

echo "::group::SDL2"
d="$(unpack sdl2)"
cmake -S "$d" -B "$WORK/sdl2-build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_OSX_ARCHITECTURES=x86_64 -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_INSTALL_RPATH="" \
    -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF -DSDL_TESTS=OFF
cmake --build "$WORK/sdl2-build" -j"$JOBS"
cmake --install "$WORK/sdl2-build"
echo "::endgroup::"

# Keep each source's licence and notice files for the engine's licences/ folder.
for key in gmp nettle gnutls freetype sdl2; do
    d="$(find "$WORK/$key" -mindepth 1 -maxdepth 1 -type d | head -1)"
    out="$PREFIX/share/licences/$key"
    mkdir -p "$out"
    find "$d" -maxdepth 1 -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'LICENCE*' \
        -o -iname 'AUTHORS*' -o -iname 'README' -o -iname 'NOTICE*' \) -exec cp {} "$out/" \;
    [ -d "$d/docs" ] && find "$d/docs" -maxdepth 1 -type f \( -iname 'FTL.TXT' -o -iname 'GPLv2.TXT' -o -iname 'LICENSE.TXT' \) -exec cp {} "$out/" \;
    ls "$out" | sed "s|^|$key: |"
done

echo "built:"
ls -la "$PREFIX/lib"/*.dylib
