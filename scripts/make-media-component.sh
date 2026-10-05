#!/usr/bin/env bash
# make-media-component.sh -- put the media libraries into the engine.
#
#   make-media-component.sh --from GSTREAMER_LIB_DIR --version VERSION --notices NOTICES_DIR \
#                           --dest ENGINE --list OUT_TSV
#
# Moved here from mavrik's own s183-engine branch (scripts/engine/make-media-component.sh) and
# changed to write straight into the engine instead of a separate archive.
#
# Wine's winegstreamer.so (GStreamer) and winedmo.so (FFmpeg) need these libraries. A new player
# has no GStreamer.framework, and a Mac that has one should never lend it to a game. So the
# engine carries a trimmed copy in its own lib/ folder (libraries) and lib/gstreamer-1.0/
# (plugins), where Wine's Unix modules find them through their own run paths.
#
# GSTREAMER_LIB_DIR is the `lib` folder of GStreamer's official macOS framework build, expanded
# from its .pkg files (never installed). The component takes:
#   - the libraries winegstreamer.so and winedmo.so link, and everything they link in turn;
#   - the plugins in PLUGINS below (the ones Wine's media paths build pipelines from), and
#     everything they link;
# each thinned to x86_64. Every file must have a line in licence_of below, and none may be GPL:
# a file without one stops the build (fail closed). Each plugin must also declare an LGPL
# licence in its own plugin descriptor (read from the binary), unless licence_of names a
# reviewed exception; FFmpeg's libraries must say "LGPL version 2.1 or later" about themselves.
#
# NOTICES_DIR must hold <project>.txt for every project (project_of below): its licence text
# and copyright notices. A project without one stops the build.
#
# OUT_TSV gets one line per file: path in the engine, SPDX licence, project, source.
#
# Bash 3.2 compatible (macOS /bin/bash). Needs otool, lipo and strings (Xcode tools).

set -euo pipefail

FROM="" VERSION="" DEST="" NOTICES="" LIST=""
while [ $# -gt 0 ]; do
    case "$1" in
        --from) FROM="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        --notices) NOTICES="$2"; shift 2 ;;
        --dest) DEST="$2"; shift 2 ;;
        --list) LIST="$2"; shift 2 ;;
        *) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
    esac
done
die() { echo "make-media-component: $*" >&2; exit 1; }
[ -n "$FROM" ] && [ -n "$VERSION" ] && [ -n "$DEST" ] && [ -n "$NOTICES" ] && [ -n "$LIST" ] \
    || die "--from, --version, --notices, --dest and --list are needed"
[ -d "$NOTICES" ] || die "no notices folder at $NOTICES"
[ -f "$FROM/libgstreamer-1.0.0.dylib" ] || die "no libgstreamer-1.0.0.dylib in $FROM"
case "$VERSION" in *[!0-9.]*|'') die "the version is digits and dots ($VERSION)" ;; esac

# What winegstreamer.so and winedmo.so link (Wine 11.0; checked with otool -L).
SEEDS="libgstvideo-1.0.0.dylib libgstaudio-1.0.0.dylib libgstbase-1.0.0.dylib libgsttag-1.0.0.dylib
libgstreamer-1.0.0.dylib libgobject-2.0.0.dylib libglib-2.0.0.dylib libintl.8.dylib
libavutil.59.dylib libavformat.61.dylib libavcodec.61.dylib"

# The plugins: Wine's pipelines (appsrc/appsink, decodebin, typefind, converters, videoflip) and the
# demuxers, parsers and decoders for the formats games ship, all LGPL. Not taken: x264,
# x265, a52dec, dvdread, dvdnav, openh264, dtsdec and mpeg2dec (GPL or patent-encumbered).
PLUGINS="app playback typefindfunctions videoconvertscale audioconvert audioresample coreelements
isomp4 matroska ogg vorbis theora opus avi wavparse audioparsers mpegpsdemux mpegtsdemux asf
id3demux apetag flac mpg123 libav videoparsersbad volume audiorate videorate pbtypes deinterlace videofilter"

# Every file the component may hold, with its SPDX licence. A file not listed stops the build.
licence_of() {
    case "$1" in
        # Declares "unknown" in its plugin descriptor; Fluendo's MPEG-PS demuxer sources are
        # under the MPL 1.1 or, at the user's choice, the LGPL (read in its source headers).
        gstreamer-1.0/libgstmpegpsdemux.dylib) echo "MPL-1.1 OR LGPL-2.1-or-later" ;;
        gstreamer-1.0/libgst*.dylib|libgst*-1.0.0.dylib) echo "LGPL-2.1-or-later" ;;
        libglib-2.0.0.dylib|libgobject-2.0.0.dylib|libgio-2.0.0.dylib|libgmodule-2.0.0.dylib) echo "LGPL-2.1-or-later" ;;
        libintl.8.dylib) echo "LGPL-2.0-or-later" ;;
        libavcodec.61.dylib|libavformat.61.dylib|libavutil.59.dylib|libavfilter.10.dylib|libswresample.5.dylib|libswscale.8.dylib) echo "LGPL-2.1-or-later" ;;
        libmpg123.0.dylib|libmpg123.1.dylib) echo "LGPL-2.1-only" ;;
        libffi.7.dylib|libffi.8.dylib) echo "MIT" ;;
        libpcre2-8.0.dylib) echo "BSD-3-Clause" ;;
        liborc-0.4.0.dylib) echo "BSD-2-Clause AND BSD-3-Clause" ;;
        libz.1.dylib) echo "Zlib" ;;
        libbz2.1.dylib|libbz2.1.0.dylib) echo "bzip2-1.0.6" ;;
        libFLAC.8.dylib|libFLAC.12.dylib|libogg.0.dylib|libvorbis.0.dylib|libvorbisenc.2.dylib|libtheoradec.1.dylib|libtheoraenc.1.dylib|libopus.0.dylib) echo "BSD-3-Clause" ;;
        *) echo "" ;;
    esac
}

# The source project whose licence text and notices cover a file (NOTICES_DIR/<project>.txt).
project_of() {
    case "$1" in
        gstreamer-1.0/libgst*.dylib|libgst*-1.0.0.dylib) echo "gstreamer" ;;
        libglib-2.0.0.dylib|libgobject-2.0.0.dylib|libgio-2.0.0.dylib|libgmodule-2.0.0.dylib) echo "glib" ;;
        libintl.8.dylib) echo "proxy-libintl" ;;
        libav*|libsw*) echo "ffmpeg" ;;
        libmpg123.*) echo "mpg123" ;;
        libffi.*) echo "libffi" ;;
        libpcre2-8.0.dylib) echo "pcre2" ;;
        liborc-0.4.0.dylib) echo "orc" ;;
        libz.1.dylib) echo "zlib" ;;
        libbz2.*) echo "bzip2" ;;
        libFLAC.*) echo "flac" ;;
        libogg.0.dylib) echo "ogg" ;;
        libvorbis.0.dylib|libvorbisenc.2.dylib) echo "vorbis" ;;
        libtheoradec.1.dylib|libtheoraenc.1.dylib) echo "theora" ;;
        libopus.0.dylib) echo "opus" ;;
        *) echo "" ;;
    esac
}

# The licence a plugin declares in its own descriptor: the string after its version
# (name, description, version, licence, source module, package, origin). `strings -n 3`,
# so a bare "GPL" shows.
declared_licence() {
    strings -n 3 -a -arch x86_64 "$1" | awk -v v="$VERSION" 'prev == v && !done { print; done = 1 } { prev = $0 }'
}

# The @rpath libraries a file links (its own name left out).
rpath_deps() {
    otool -L -arch x86_64 "$1" | tail -n +2 | awk '{print $1}' | sed -n 's|^@rpath/||p' | grep -v -x "$(basename "$1")" || true
}

LIBDEST="$DEST/lib"
mkdir -p "$LIBDEST/gstreamer-1.0" "$(dirname "$LIST")"
: > "$LIST"

TODO=""
for p in $PLUGINS; do TODO="$TODO gstreamer-1.0/libgst$p.dylib"; done
TODO="$TODO $SEEDS"
DONE=" "
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    NEXT=""
    for f in $TODO; do
        case "$DONE" in *" $f "*) continue ;; esac
        DONE="$DONE$f "
        src="$FROM/$f"
        [ -e "$src" ] || die "$f is not in $FROM"
        licence="$(licence_of "$f")"
        [ -n "$licence" ] || die "$f has no licence line; add it only after reading its licence"
        case "$licence" in *GPL*) case "$licence" in *LGPL*) ;; *) die "$f is $licence" ;; esac ;; esac
        case "$licence" in GPL*|*" AND GPL"*) die "$f is $licence" ;; esac
        project="$(project_of "$f")"
        [ -n "$project" ] || die "$f has no project for its notices"
        [ -s "$NOTICES/$project.txt" ] || die "no licence text and notices for $project ($NOTICES/$project.txt)"
        case "$f" in
            gstreamer-1.0/*)
                declared="$(declared_licence "$src")"
                case "$licence:$declared" in
                    LGPL*:LGPL) ;;
                    "MPL-1.1 OR LGPL-2.1-or-later:unknown") ;;
                    *) die "$f declares its licence as '${declared:-nothing}', not what licence_of says ($licence)" ;;
                esac
                ;;
            libav*|libsw*)
                strings -a -arch x86_64 "$src" | grep "LGPL version 2.1 or later" >/dev/null \
                    || die "$f does not say it is LGPL 2.1 or later"
                ;;
        esac
        [ ! -e "$LIBDEST/$f" ] || die "$f is already in the engine's lib folder (two components want it)"
        lipo -thin x86_64 "$src" -output "$LIBDEST/$f" 2>/dev/null || cp -L "$src" "$LIBDEST/$f"
        [ "$(lipo -archs "$LIBDEST/$f")" = "x86_64" ] || die "$f is not x86_64 only after thinning"
        chmod 0644 "$LIBDEST/$f"
        printf '%s\t%s\t%s\tGStreamer %s official macOS build\n' "lib/$f" "$licence" "$project" "$VERSION" >> "$LIST"
        for d in $(rpath_deps "$src"); do NEXT="$NEXT $d"; done
    done
    TODO="$NEXT"
    [ -n "${TODO// /}" ] || break
done
[ -z "${TODO// /}" ] || die "the dependency walk did not end"
echo "media component: $(wc -l < "$LIST" | tr -d ' ') files, $(du -sk "$LIBDEST" | cut -f1) KB in lib/ so far"
