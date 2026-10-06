# toolchain.sh INPUTS -- sourced by build.sh, assemble.sh, gates.sh and pack.sh (". toolchain.sh INPUTS").
#
# Selects the Xcode that inputs.json pins (toolchain.xcode: version and build), checks it, and
# exports DEVELOPER_DIR, so clang, the macOS SDK, strip, otool and codesign are the same in every
# step, on GitHub and on a Mac. Homebrew's bison 3 (keg-only) goes first in PATH, so the cache keys
# and the build see the same bison. The Wine loader's SDK version decides which AppKit behaviours its
# windows get, so an engine built against another SDK is a different engine.
#
# A DEVELOPER_DIR already set is checked, not replaced. Otherwise the first of these that holds the
# pinned Xcode is taken: /Applications/Xcode_<version>.app (GitHub's runner images), the Xcode
# xcode-select points at, /Applications/Xcode.app. When GITHUB_ENV is set, DEVELOPER_DIR is also
# written there for the workflow's later steps.

_tc_inputs="$1"
_tc_pin() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["toolchain"]["xcode"][sys.argv[2]])' "$_tc_inputs" "$1"; }
_tc_version="$(_tc_pin version)"
_tc_build="$(_tc_pin build)"
_tc_matches() {  # _tc_matches DEVELOPER_DIR: true when it is the pinned Xcode
    [ -x "$1/usr/bin/xcodebuild" ] || return 1
    local v
    v="$(DEVELOPER_DIR="$1" "$1/usr/bin/xcodebuild" -version 2>/dev/null | paste -sd ' ' -)"
    [ "$v" = "Xcode $_tc_version Build version $_tc_build" ]
}
if [ -z "${DEVELOPER_DIR:-}" ]; then
    for _tc_app in "/Applications/Xcode_${_tc_version}.app" "$(xcode-select -p 2>/dev/null | sed 's|/Contents/Developer$||')" /Applications/Xcode.app; do
        if [ -n "$_tc_app" ] && _tc_matches "$_tc_app/Contents/Developer"; then
            DEVELOPER_DIR="$_tc_app/Contents/Developer"
            break
        fi
    done
fi
if [ -z "${DEVELOPER_DIR:-}" ] || ! _tc_matches "$DEVELOPER_DIR"; then
    echo "::error::Xcode $_tc_version ($_tc_build) is needed (inputs.json, toolchain.xcode); DEVELOPER_DIR=${DEVELOPER_DIR:-unset} is not it"
    exit 1
fi
export DEVELOPER_DIR
[ -z "${GITHUB_ENV:-}" ] || echo "DEVELOPER_DIR=$DEVELOPER_DIR" >> "$GITHUB_ENV"
for _tc_bison in /opt/homebrew/opt/bison/bin /usr/local/opt/bison/bin; do
    if [ -x "$_tc_bison/bison" ]; then
        case ":$PATH:" in *":$_tc_bison:"*) ;; *) PATH="$_tc_bison:$PATH" ;; esac
        [ -z "${GITHUB_PATH:-}" ] || echo "$_tc_bison" >> "$GITHUB_PATH"
        break
    fi
done
export PATH
unset -f _tc_pin _tc_matches
unset _tc_inputs _tc_version _tc_build _tc_app _tc_bison
