#!/bin/bash
# fetch-release-sources.sh DEST [--list]
#
# Downloads the release sources that are not on GitHub (so the GitHub CLI cannot fetch them) into
# DEST, for a Mac build that uses FETCH_ARGS="--via gh --from DEST". These are the entries of
# inputs.json's release_sources whose address is not on github.com: today Wine Gecko's source, the
# six GStreamer 1.28.6 tarballs, GLib 2.82.4 and FFmpeg 7.1.
#
# Each file is saved under the last part of its address (the name fetch.py looks for in --from),
# and checked against every value inputs.json pins for it. A file already in DEST that matches is
# kept, not downloaded again. A download that does not match its pinned sha256 or size is kept as
# NAME.mismatch, never under its real name, and the script ends with an error.
#
# At the end it prints each file's size and sha256, and the values still to pin in inputs.json (a
# size for all of them, and also a sha256 for Wine Gecko's source, which has no pin yet: compare it
# with a second source before pinning it). For that file the script also checks the SHA-512 Fedora's
# mingw-wine-gecko package pins for it (its dist-git `sources` file, as mirrored on GitHub in
# praiskup/fedora-sources-statistics; Fedora's own site could not be read by the agent that wrote this).
# Pinning them is a separate change, checked by `python3 scripts/fetch.py check-pins inputs.json`.
#
# --list prints what would be fetched and downloads nothing.
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
INPUTS="$REPO/inputs.json"
mkdir -p "$1"
DEST="$(cd "$1" && pwd)"
LIST=""
[ "${2:-}" = "--list" ] && LIST=1

# key<TAB>url<TAB>size or -<TAB>sha256 or -, one line per release source not on GitHub
sources="$(python3 -I - "$INPUTS" <<'EOF'
import json, sys
doc = json.load(open(sys.argv[1]))
for key, e in doc.get("release_sources", {}).items():
    url = e["url"]
    if url.startswith(("https://github.com/", "https://api.github.com/", "https://raw.githubusercontent.com/")):
        continue
    print("\t".join([key, url, str(e.get("size") or "-"), e.get("sha256") or "-"]))
EOF
)"
[ -n "$sources" ] || { echo "no release source outside GitHub in $INPUTS"; exit 0; }

if [ -n "$LIST" ]; then
    echo "would fetch into $DEST:"
    printf '%s\n' "$sources" | while IFS=$'\t' read -r key url size sha; do
        echo "  $key: $url (size $size, sha256 $sha)"
    done
    exit 0
fi

sha_of() { shasum -a 256 "$1" | cut -d' ' -f1; }
size_of() { stat -f %z "$1"; }
# A second published value for the one source with no sha256 pin (see the header).
GECKO_SRC_SHA512_FEDORA=707dec36ae0481a81b83684d27f95b414531fe4a98b4bc7b738013ba3f510945239964993499c2ffea95ae1c9518d08aa46de99b3c0503a310bf7ff31fdf9312

bad=0
summary=""
pins=""
while IFS=$'\t' read -r key url size sha; do
    name="${url##*/}"
    file="$DEST/$name"
    echo "$key: $url"
    if [ ! -f "$file" ]; then
        part="$file.part"
        rm -f "$part"
        if ! curl -fL --retry 3 --retry-delay 5 --connect-timeout 30 -sS -o "$part" "$url"; then
            echo "  FAILED to download"
            rm -f "$part"
            bad=1
            summary="$summary$key	-	-	download failed\n"
            continue
        fi
        mv "$part" "$file"
    else
        echo "  already in $DEST"
    fi
    got_size="$(size_of "$file")"
    got_sha="$(sha_of "$file")"
    verdict="ok"
    if [ "$sha" != "-" ] && [ "$got_sha" != "$sha" ]; then verdict="sha256 does not match the pin $sha"; fi
    if [ "$size" != "-" ] && [ "$got_size" != "$size" ]; then verdict="size does not match the pin $size"; fi
    if [ "$key" = wine-gecko-source ] && [ "$verdict" = ok ]; then
        if [ "$(shasum -a 512 "$file" | cut -d' ' -f1)" = "$GECKO_SRC_SHA512_FEDORA" ]; then
            echo "  SHA-512 matches the one Fedora's mingw-wine-gecko package pins"
        else
            verdict="SHA-512 does not match the one Fedora's mingw-wine-gecko package pins"
        fi
    fi
    if [ "$verdict" != "ok" ]; then
        mv "$file" "$file.mismatch"
        echo "  MISMATCH: $verdict; kept as $name.mismatch"
        bad=1
    else
        echo "  $got_size bytes, sha256 $got_sha"
        if [ "$size" = "-" ] || [ "$sha" = "-" ]; then
            pins="$pins  \"$key\": {\"size\": $got_size, \"sha256\": \"$got_sha\"}\n"
        fi
    fi
    summary="$summary$key	$got_size	$got_sha	$verdict\n"
done <<< "$sources"

echo
echo "key	size	sha256	result"
printf "%b" "$summary"
if [ -n "$pins" ]; then
    echo
    echo "values to pin in inputs.json (release_sources):"
    printf "%b" "$pins"
fi
exit "$bad"
