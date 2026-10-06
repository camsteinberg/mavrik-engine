#!/bin/bash
# build-deps.sh PATHS_JSON WORK PREFIX [LIBRARY...]
#
# Builds the Unix libraries Wine loads at run time from their pinned source tarballs
# (inputs.json): gmp, nettle, gnutls, freetype and SDL2, for x86_64, into PREFIX. WORK is scratch
# space for the sources and build trees, removed when the build succeeds.
# Each is built with the fewest options that still give Wine what it uses, so the
# engine carries as few extra libraries as it can:
#   gnutls  - with its own copies of libtasn1 and libunistring, no p11-kit, no IDN,
#             no compression, no gettext. Wine uses it for TLS and its crypto calls. Its
#             system-wide priority file is turned off (an empty --with-system-priority-file),
#             so GnuTLS reads no configuration from outside the engine.
#   freetype - no harfbuzz, png or brotli; zlib and bzip2 come from macOS.
#   gmp and nettle - "fat" builds that pick their CPU code at run time, so one build is
#             safe on every Intel Mac and under Rosetta.
# Each configure and make runs as x86_64 (through Rosetta on Apple silicon), so the libraries are
# built exactly as on an Intel Mac; SDL2's CMake build runs natively and compiles for x86_64. Every
# compiler gets -ffile-prefix-map, so the build folders' paths stay out of the libraries.
# Each library's licence and notice files are kept for the engine's licences/ folder: the top-level
# ones, and the notices of third-party code built into it (NOTICES below). Every licence-named file
# deeper in a source tree must be listed in NOTICES or in NOT_SHIPPED with its reason, so a new
# version that brings in more third-party code stops the build until its notices are reviewed.
# JOBS sets make's parallel jobs. Naming libraries builds only
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

MAP="-ffile-prefix-map=$WORK/=deps-src/ -ffile-prefix-map=$PREFIX/=deps/"
export CC="ccache clang -arch x86_64" CXX="ccache clang++ -arch x86_64"
export CFLAGS="-O2 $MAP" CXXFLAGS="-O2 $MAP"
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
    --with-system-priority-file= \
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
    -DCMAKE_C_FLAGS="$MAP" -DCMAKE_OBJC_FLAGS="$MAP" \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_OBJC_COMPILER_LAUNCHER=ccache -DCMAKE_INSTALL_RPATH="" \
    -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF -DSDL_TESTS=OFF
cmake --build "$WORK/sdl2-build" -j"$JOBS"
cmake --install "$WORK/sdl2-build"
echo "::endgroup::"
fi

# Licence and notice files. NOTICES: kept, besides the top-level ones (path in the source tree).
# NOT_SHIPPED: licence-named files deeper in the tree that are not about code in the library.
NOTICES_gmp=""
NOTICES_nettle="descore.README"
NOTICES_gnutls="lib/accelerated/x86/license.txt lib/inih/LICENSE.txt lib/crau/LICENSE"
NOTICES_freetype="docs/FTL.TXT docs/GPLv2.TXT src/bdf/README src/pcf/README"
NOTICES_sdl2="src/hidapi/LICENSE.txt src/hidapi/LICENSE-bsd.txt src/video/yuv2rgb/LICENSE"
not_shipped() {  # not_shipped KEY PATH: the reason a licence file is not shipped, or nothing
    case "$1:$2" in
        gnutls:lib/crau/UNLICENSE) echo "crypto-auditing is MIT or Unlicense; the MIT terms are taken" ;;
        gnutls:doc/*) echo "documentation and example programs, not built" ;;
        sdl2:src/hidapi/LICENSE-gpl3.txt|sdl2:src/hidapi/LICENSE-orig.txt)
            echo "HIDAPI is offered under GPL-3.0, BSD or its original licence; the BSD terms are taken" ;;
        sdl2:Xcode-iOS/*|sdl2:Xcode/*) echo "Xcode project files and iOS demos, not built" ;;
        sdl2:test/*|sdl2:visualtest/*) echo "tests, not built" ;;
    esac
}
for key in gmp nettle gnutls freetype sdl2; do
    want "$key" || continue
    d="$(find "$WORK/$key" -mindepth 1 -maxdepth 1 -type d | sed -n "1,1p")"
    out="$PREFIX/share/licences/$key"
    mkdir -p "$out"
    find "$d" -maxdepth 1 -type f \( -iname 'COPYING*' -o -iname 'LICENSE*' -o -iname 'LICENCE*' \
        -o -iname 'AUTHORS*' -o -iname 'README' -o -iname 'NOTICE*' \) -exec cp {} "$out/" \;
    notices="$(eval echo "\$NOTICES_$key")"
    for n in $notices; do
        [ -f "$d/$n" ] || { echo "::error::$key: notice $n is not in the source"; exit 1; }
        mkdir -p "$out/$(dirname "$n")"
        cp "$d/$n" "$out/$n"
    done
    unknown=""
    while IFS= read -r f; do
        rel="${f#"$d"/}"
        case "$rel" in */*) ;; *) continue ;; esac  # top-level files are kept above
        case " $notices " in *" $rel "*) continue ;; esac
        [ -n "$(not_shipped "$key" "$rel")" ] && continue
        unknown="$unknown $rel"
    done < <(find "$d" -type f | awk -F/ '{l=tolower($NF); if (l ~ /^(licen[cs]e|copying|copyright|notice|unlicense|patents)/ || l ~ /\.licen[cs]e$/) print}' | sort)
    [ -z "$unknown" ] || { echo "::error::$key: licence files not reviewed (add each to NOTICES_$key or not_shipped):$unknown"; exit 1; }
    (cd "$out" && find . -type f | sed "s|^\./|$key: |" | sort)
done

echo "built:"
ls -la "$PREFIX/lib"/*.dylib
# WORK only held sources and build trees; every build unpacks afresh, so they go.
rm -rf "$WORK"
