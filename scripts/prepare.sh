#!/bin/bash
# prepare.sh PATHS_JSON INPUTS_JSON WORK
#
# 1. Unpacks the pinned CrossOver sources and keeps sources/wine as WORK/wine-src.
# 2. Stops if dlls/appwiz.cpl/addons.c names a Wine Mono or Gecko version that inputs.json
#    has not pinned (the engine must carry exactly what the tree asks for).
# 3. Applies patches/*.patch in order; any reject or fuzz stops the build.
# 4. Expands GStreamer's runtime and development packages (without installing anything
#    into /Library) into WORK/gstreamer/Versions/1.0, and points its pkg-config files there.
set -euo pipefail

PATHS="$1" INPUTS="$2" WORK="$3"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
src() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PATHS" "$1"; }
pin() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))["inputs"]; print(d[sys.argv[2]][sys.argv[3]])' "$INPUTS" "$1" "$2"; }

mkdir -p "$WORK"
echo "::group::CrossOver sources"
rm -rf "$WORK/cx" "$WORK/wine-src"
mkdir -p "$WORK/cx"
tar -xzf "$(src crossover-sources)" -C "$WORK/cx"
echo "top level of the source archive:"
find "$WORK/cx" -mindepth 1 -maxdepth 2 | sed "s|$WORK/cx/||" | sort | sed -n "1,80p"
subdir="$(pin crossover-sources subdir)"
mv "$WORK/cx/$subdir" "$WORK/wine-src"
cat "$WORK/wine-src/VERSION"
echo "::endgroup::"

echo "::group::addons.c versions"
addons="$WORK/wine-src/dlls/appwiz.cpl/addons.c"
python3 "$REPO/scripts/gates.py" addons-source "$addons" "$INPUTS"
echo "::endgroup::"

echo "::group::patches"
cd "$WORK/wine-src"
for p in "$REPO"/patches/*.patch; do
    [ -e "$p" ] || continue
    echo "applying $(basename "$p")"
    if ! patch -p1 --forward --batch --fuzz=0 --no-backup-if-mismatch < "$p"; then
        echo "::error::$(basename "$p") does not apply cleanly"
        exit 1
    fi
done
rejects="$(find . -name '*.rej' -o -name '*.orig' | sed -n "1,5p")"
[ -z "$rejects" ] || { echo "::error::patch leftovers: $rejects"; exit 1; }
cd - >/dev/null
echo "::endgroup::"

echo "::group::GStreamer packages"
G="$WORK/gstreamer"
rm -rf "$G" "$WORK/gst-pkg"
mkdir -p "$G"
for key in gstreamer-runtime gstreamer-devel; do
    pkgutil --expand-full "$(src "$key")" "$WORK/gst-pkg/$key"
    # Each component package's Payload is a slice of GStreamer.framework.
    for payload in "$WORK/gst-pkg/$key"/*.pkg/Payload; do
        [ -d "$payload" ] || continue
        ditto "$payload" "$G"
    done
done
lib="$(find "$G" -name libgstreamer-1.0.0.dylib -path '*/lib/*' | sed -n "1,1p")"
[ -n "$lib" ] || { echo "::error::no libgstreamer in the expanded packages"; find "$G" -maxdepth 4 | sed -n "1,40p"; exit 1; }
ROOT="$(cd "$(dirname "$lib")/.." && pwd)"
echo "component packages:"; ls "$WORK/gst-pkg/gstreamer-runtime" "$WORK/gst-pkg/gstreamer-devel"
# The .pc files name the framework's install place; point them at the expanded copy.
pcdir="$ROOT/lib/pkgconfig"
[ -d "$pcdir" ] || { echo "::error::no pkg-config files in the development package"; exit 1; }
for pc in "$pcdir"/*.pc; do
    sed -i '' "s|/Library/Frameworks/GStreamer.framework/Versions/1.0|$ROOT|g; s|/Library/Frameworks/GStreamer.framework|$G|g" "$pc"
done
/usr/bin/grep -h '^prefix=' "$pcdir/gstreamer-1.0.pc" "$pcdir/glib-2.0.pc"
ls "$pcdir" | /usr/bin/grep -E '^(libav|libsw|gstreamer|glib)' | tr '\n' ' ' || true; echo
echo "::endgroup::"
echo "GST_ROOT=$ROOT"
echo "$ROOT" > "$WORK/gst-root.path"
