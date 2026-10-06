#!/bin/bash
# build-deps.sh PATHS_JSON WORK PREFIX [LIBRARY...]
#
# Builds the Unix libraries Wine loads at run time from their pinned source tarballs
# (inputs.json): gmp, nettle, gnutls, freetype and SDL2, for x86_64, into PREFIX. WORK is scratch
# space for the sources and build trees, removed when the build succeeds.
# Each is built with the fewest options that still give Wine what it uses, so the
# engine carries as few extra libraries as it can:
#   gnutls  - with its own copies of libtasn1 and libunistring, no p11-kit, no IDN,
#             no compression, no gettext. Wine uses it for TLS and its crypto calls.
#   freetype - no harfbuzz, png or brotli; zlib and bzip2 come from macOS.
#   gmp and nettle - "fat" builds that pick their CPU code at run time, so one build is
#             safe on every Intel Mac and under Rosetta.
# Each configure and make runs as x86_64 (through Rosetta on Apple silicon), so the libraries are
# built exactly as on an Intel Mac. JOBS sets make's parallel jobs. Naming libraries builds only
# those, into the existing PREFIX (to retry one); with none named, PREFIX is emptied first.
set -euo pipefail

PATHS="$1" WORK="$2" PREFIX="$3"
shift 3
ONLY=" $* "
want() { [ "$ONLY" = "  " ] || case "$ONLY" in *" $1 "*) true ;; *) false ;; esac; }
if [ "$ONLY" = "  " ]; then rm -rf "$PREFIX"; fi
mkdir -p "$WORK" "$PREFIX"
: "${MACOSX_DEPLOYMENT_TARGET:?set MACOSX_DEPLOYMENT_TARGET}"
JOBS="${JOBS:-$(( $(sysctl -n hw.ncpu) + 1 ))}"
x86() { arch -x86_64 "$@"; }

src() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PATHS" "$1"; }
unpack() {  # unpack KEY -> echoes the source folder
    local archive dir
    archive="$(src "$1")"
    dir="$WORK/$1"
    rm -rf "$dir" && mkdir -p "$dir"
    tar -xf "$archive" -C "$dir"
    find "$dir" -mindepth 1 -maxdepth 1 -type d | sed -n "1,1p"
}

export CC="ccache clang -arch x86_64" CXX="ccache clang++ -arch x86_64"
export CFLAGS="-O2" CXXFLAGS="-O2"
export CPPFLAGS="-I$PREFIX/include"
export LDFLAGS="-L$PREFIX/lib -Wl,-headerpad_max_install_names"
# Only our own .pc files: nothing from Homebrew on the runner may be found by accident.
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"

common=(--prefix="$PREFIX" --enable-shared --disable-static)

if want gmp; then
echo "::group::gmp"
d="$(unpack gmp)"
( cd "$d" && x86 ./configure "${common[@]}" --enable-fat --disable-cxx && x86 make -j"$JOBS" && x86 make install )
echo "::endgroup::"
fi

if want nettle; then
echo "::group::nettle"
d="$(unpack nettle)"
( cd "$d" && x86 ./configure "${common[@]}" --enable-fat --disable-documentation --disable-openssl \
    && x86 make -j"$JOBS" && x86 make install )
echo "::endgroup::"
fi

if want gnutls; then
echo "::group::gnutls"
d="$(unpack gnutls)"
( cd "$d" && x86 ./configure "${common[@]}" \
    --disable-doc --disable-manpages --disable-tests --disable-full-test-suite --disable-tools \
    --disable-cxx --disable-guile --disable-nls --disable-libdane \
    --with-included-libtasn1 --with-included-unistring \
    --without-p11-kit --without-idn --without-tpm --without-tpm2 \
    --without-brotli --without-zstd --without-zlib --without-leancrypto \
    && x86 make -j"$JOBS" && x86 make install )
echo "::endgroup::"
fi

if want freetype; then
echo "::group::freetype"
d="$(unpack freetype)"
( cd "$d" && x86 ./configure "${common[@]}" --without-harfbuzz --without-png --without-brotli \
    --with-zlib=yes --with-bzip2=yes && x86 make -j"$JOBS" && x86 make install )
echo "::endgroup::"
fi

if want sdl2; then
echo "::group::SDL2"
d="$(unpack sdl2)"
rm -rf "$WORK/sdl2-build"
cmake -S "$d" -B "$WORK/sdl2-build" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_OSX_ARCHITECTURES=x86_64 -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET" \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_OBJC_COMPILER=clang \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_OBJC_COMPILER_LAUNCHER=ccache -DCMAKE_INSTALL_RPATH="" \
    -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF -DSDL_TESTS=OFF
cmake --build "$WORK/sdl2-build" -j"$JOBS"
cmake --install "$WORK/sdl2-build"
echo "::endgroup::"
fi

# Keep each source's licence and notice files for the engine's licences/ folder.
for key in gmp nettle gnutls freetype sdl2; do
    want "$key" || continue
    d="$(find "$WORK/$key" -mindepth 1 -maxdepth 1 -type d | sed -n "1,1p")"
    out="$PREFIX/share/licences/$key"
    mkdir -p "$out"
    find "$d" -maxdepth 1 -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'LICENCE*' \
        -o -iname 'AUTHORS*' -o -iname 'README' -o -iname 'NOTICE*' \) -exec cp {} "$out/" \;
    [ -d "$d/docs" ] && find "$d/docs" -maxdepth 1 -type f \( -iname 'FTL.TXT' -o -iname 'GPLv2.TXT' -o -iname 'LICENSE.TXT' \) -exec cp {} "$out/" \;
    ls "$out" | sed "s|^|$key: |"
done

echo "built:"
ls -la "$PREFIX/lib"/*.dylib
# WORK only held sources and build trees; every build unpacks afresh, so they go.
rm -rf "$WORK"
