#!/bin/bash
# prepare.sh PATHS_JSON INPUTS_JSON WORK
#
# 1. Unpacks sources/wine from the pinned CrossOver sources as WORK/wine-src.
# 2. Stops if dlls/appwiz.cpl/addons.c names a Wine Mono or Gecko version that inputs.json
#    has not pinned (the engine must carry exactly what the tree asks for).
# 3. Applies patches/*.patch in order; any reject or fuzz stops the build.
# 4. Expands GStreamer's runtime and development packages (without installing anything
#    into /Library, and without their static archives) into WORK/gstreamer/Versions/1.0, and
#    points its pkg-config files there.
set -euo pipefail

PATHS="$1" INPUTS="$2" WORK="$3"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
src() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PATHS" "$1"; }
pin() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))["inputs"]; print(d[sys.argv[2]][sys.argv[3]])' "$INPUTS" "$1" "$2"; }

mkdir -p "$WORK"
echo "::group::CrossOver sources"
rm -rf "$WORK/cx" "$WORK/wine-src"
mkdir -p "$WORK/cx"
subdir="$(pin crossover-sources subdir)"
# Only the Wine tree: the rest of the archive (CrossOver's other sources) is not built here.
tar -xzf "$(src crossover-sources)" -C "$WORK/cx" "$subdir"
mv "$WORK/cx/$subdir" "$WORK/wine-src"
rm -rf "$WORK/cx"
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
mkdir -p "$G" "$WORK/gst-pkg"
FW=/Library/Frameworks/GStreamer.framework
for key in gstreamer-runtime gstreamer-devel; do
    pkgutil --expand "$(src "$key")" "$WORK/gst-pkg/$key"
    echo "$key component packages: $(ls "$WORK/gst-pkg/$key" | tr '\n' ' ')"
    # Each component package's Payload is a slice of GStreamer.framework, placed where its
    # PackageInfo says it installs (the framework itself, or Versions/1.0 inside it). Static
    # archives are never written: Wine links GStreamer's shared libraries, and they are 4.5 GB.
    for component in "$WORK/gst-pkg/$key"/*.pkg; do
        [ -f "$component/Payload" ] || continue
        loc="$(sed -n 's/.*install-location="\([^"]*\)".*/\1/p' "$component/PackageInfo" | sed -n 1p)"
        case "$loc" in
            "$FW"|"$FW"/*) ;;
            *) echo "::error::$(basename "$component") installs to '$loc', outside $FW"; exit 1 ;;
        esac
        mkdir -p "$G${loc#"$FW"}"
        aa extract -i "$component/Payload" -d "$G${loc#"$FW"}" -exclude-regex '\.a$'
        rm -rf "$component"
    done
    rm -rf "$WORK/gst-pkg/$key"
done
rmdir "$WORK/gst-pkg"
lib="$(find "$G" -name libgstreamer-1.0.0.dylib -path '*/lib/*' | sed -n "1,1p")"
[ -n "$lib" ] || { echo "::error::no libgstreamer in the expanded packages"; find "$G" -maxdepth 4 | sed -n "1,40p"; exit 1; }
ROOT="$(cd "$(dirname "$lib")/.." && pwd)"
# The .pc files name the framework's install place; point them at the expanded copy.
pcdir="$ROOT/lib/pkgconfig"
[ -d "$pcdir" ] || { echo "::error::no pkg-config files in the development package"; exit 1; }
for pc in "$pcdir"/*.pc; do
    [ -L "$pc" ] && continue  # an alias of another .pc file here, which is edited itself
    sed -i '' "s|/Library/Frameworks/GStreamer.framework/Versions/1.0|$ROOT|g; s|/Library/Frameworks/GStreamer.framework|$G|g" "$pc"
done
/usr/bin/grep -h '^prefix=' "$pcdir/gstreamer-1.0.pc" "$pcdir/glib-2.0.pc"
ls "$pcdir" | /usr/bin/grep -E '^(libav|libsw|gstreamer|glib)' | tr '\n' ' ' || true; echo
echo "::endgroup::"
echo "GST_ROOT=$ROOT"
echo "$ROOT" > "$WORK/gst-root.path"
