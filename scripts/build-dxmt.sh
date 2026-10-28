#!/bin/bash
# build-dxmt.sh WORK
#
# Builds DXMT's 64-bit files from the pinned source with this repository's patches (dxmt/patches), as
# DXMT's own CI job build-gcc-release-x86_64-windows-cross does, into WORK/dxmt-install:
#   1. LLVM 15.0.7 for x86_64 macOS with the CI's options (inputs.json, dxmt-llvm-source), installed into
#      WORK/dxmt-llvm. Its build and source folders go once it is installed; the install stays as a cache
#      for the next build with the same key (buildinfo.py keys: dxmt-llvm).
#   2. DXMT's source unpacked into /tmp/mavrik-engine-dxmt-src (SRC_ROOT), each patch applied in order (no
#      fuzz, no offset; any other result stops the build). Apple's Metal compiler writes each shader's real
#      source path into the AIR that winemetal.so embeds and takes no prefix map, so the source sits at this
#      fixed place: the files then name no machine's folders and come out the same on any Mac.
#   3. DXMT's version string. Its meson asks `git describe --always`, which the source archive cannot
#      answer, so a stand-in `git` on PATH answers <commit, 10 characters>-mavrik.<number of patches>: the
#      HUD and DXMT's log then name the commit and that the build carries mavrik's patches.
#   4. meson setup, compile and install with the CI's options (dxmt-source meson_options), linked
#      against 3Shain's Wine 8.16 (dxmt-wine), with the CI's macOS target (dxmt-source deployment_target).
# Every compiler gets -ffile-prefix-map=WORK/=, so no build path lands in the files (the Metal shaders: step 2). Called by build.sh after
# the toolchain step (DEVELOPER_DIR, PATH with Homebrew's mingw-w64 and CMake already set). A finished
# WORK/dxmt-install holds the build's key in .stamp and is skipped by the next build with the same key.
# WORK/dxmt-install/.build/dxmt.json records the commit, the version string, the patches and the tools;
# .build/winemetal_unix.c is the patched source the winemac gate reads.
set -euo pipefail

[ $# -eq 1 ] || { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(cd "$1" && pwd)"
S="$REPO/scripts"
INPUTS="$(cat "$WORK/inputs.path")"
PATHS="$WORK/downloads/paths.json"
src() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$PATHS" "$1"; }
pin() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))["inputs"][sys.argv[2]][sys.argv[3]]; print(" ".join(v) if isinstance(v, list) else v)' "$INPUTS" "$1" "$2"; }
key() { python3 "$S/buildinfo.py" keys "$INPUTS" | sed -n "s/^$1=//p"; }
fresh() { [ -n "${FRESH:-}" ] || [ ! -f "$1/.stamp" ] || [ "$(cat "$1/.stamp")" != "$2" ]; }
SRC_ROOT=/tmp/mavrik-engine-dxmt-src
MAP="-ffile-prefix-map=$WORK/="
SRC_MAP="$MAP -ffile-prefix-map=$SRC_ROOT/= -ffile-prefix-map=/private$SRC_ROOT/="
TARGET="$(pin dxmt-source deployment_target)"
VENV="$WORK/dxmt-venv"

# The build's own meson and ninja, from their pinned wheels.
# (The ninja wheel reports its version with a suffix, 1.13.2.git.kitware...)
if [ ! -x "$VENV/bin/meson" ] || [ "$("$VENV/bin/meson" --version)" != "$(pin meson version)" ] \
    || [[ "$("$VENV/bin/ninja" --version)" != "$(pin ninja version)"* ]]; then
    rm -rf "$VENV" "$WORK/dxmt-wheels"
    python3 -m venv "$VENV"
    # pip reads a wheel's tags from its file name, so each gets its own name back.
    mkdir -p "$WORK/dxmt-wheels"
    for w in meson ninja; do cp "$(src $w)" "$WORK/dxmt-wheels/$(basename "$(pin $w url)")"; done
    "$VENV/bin/pip" install --quiet --no-index --no-deps "$WORK"/dxmt-wheels/*.whl
    rm -rf "$WORK/dxmt-wheels"
fi
echo "meson $("$VENV/bin/meson" --version), ninja $("$VENV/bin/ninja" --version), $(python3 --version)"

llvm_key="$(key dxmt-llvm)"
if fresh "$WORK/dxmt-llvm" "$llvm_key"; then
    echo "::group::LLVM $(pin dxmt-llvm-source version) for DXMT"
    rm -rf "$WORK/dxmt-llvm" "$WORK/dxmt-llvm-src" "$WORK/dxmt-llvm-build"
    mkdir -p "$WORK/dxmt-llvm-src"
    tar -xJf "$(src dxmt-llvm-source)" -C "$WORK/dxmt-llvm-src"
    tar -xJf "$(src dxmt-llvm-cmake)" -C "$WORK/dxmt-llvm-src"
    v="$(pin dxmt-llvm-source version)"
    mv "$WORK/dxmt-llvm-src/llvm-$v.src" "$WORK/dxmt-llvm-src/llvm"
    mv "$WORK/dxmt-llvm-src/cmake-$v.src" "$WORK/dxmt-llvm-src/cmake"
    # shellcheck disable=SC2046  # the pinned options are one word each
    cmake -B "$WORK/dxmt-llvm-build" -S "$WORK/dxmt-llvm-src/llvm" -G Ninja \
        -DCMAKE_MAKE_PROGRAM="$VENV/bin/ninja" \
        -DCMAKE_INSTALL_PREFIX="$WORK/dxmt-llvm" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="$TARGET" \
        -DCMAKE_C_FLAGS="$MAP" \
        -DCMAKE_CXX_FLAGS="$(pin dxmt-llvm-source cxx_flags) $MAP" \
        $(pin dxmt-llvm-source cmake_options)
    cmake --build "$WORK/dxmt-llvm-build"
    cmake --install "$WORK/dxmt-llvm-build" > "$WORK/dxmt-llvm-install.log"
    rm -rf "$WORK/dxmt-llvm-src" "$WORK/dxmt-llvm-build"
    echo "$llvm_key" > "$WORK/dxmt-llvm/.stamp"
    echo "::endgroup::"
else
    echo "LLVM for DXMT: already built for $llvm_key"
fi

dxmt_key="$(key dxmt)"
if ! fresh "$WORK/dxmt-install" "$dxmt_key"; then
    echo "DXMT: already built for $dxmt_key"
    exit 0
fi

echo "::group::DXMT $(pin dxmt-source version)"
B="$WORK/dxmt-build" I="$WORK/dxmt-install" W="$WORK/dxmt-wine" SHIM="$WORK/dxmt-git"
rm -rf "$SRC_ROOT" "$WORK/dxmt-src" "$B" "$I" "$W" "$SHIM"
# /tmp is shared by every account: the folder must be new, this user's, private and not a link, and it goes when
# this script ends, whatever happens (a second build would stop here rather than share it).
mkdir -m 700 "$SRC_ROOT" || { echo "::error::$SRC_ROOT could not be made fresh (another build, or another account's)"; exit 1; }
[ ! -L "$SRC_ROOT" ] && [ -O "$SRC_ROOT" ] || { echo "::error::$SRC_ROOT is a link or not this user's"; exit 1; }
trap 'rm -rf "$SRC_ROOT"' EXIT
mkdir -p "$W" "$SHIM"
tar -xzf "$(src dxmt-source)" -C "$SRC_ROOT"
D="$SRC_ROOT/$(pin dxmt-source root)"
[ -f "$D/meson.build" ] || { echo "::error::no meson.build in the DXMT source at $D"; exit 1; }
tar -xzf "$(src dxmt-wine)" -C "$W"
[ -x "$W/bin/winebuild" ] || { echo "::error::3Shain's Wine has no bin/winebuild"; exit 1; }

n=0
for p in "$REPO"/dxmt/patches/*.patch; do
    [ -e "$p" ] || continue
    echo "applying $(basename "$p")"
    if ! log="$(patch -d "$D" -p1 --forward --batch --fuzz=0 --no-backup-if-mismatch < "$p")"; then
        echo "$log"; echo "::error::$(basename "$p") does not apply cleanly"; exit 1
    fi
    echo "$log"
    if echo "$log" | grep -qi 'offset'; then
        echo "::error::$(basename "$p") applies only at an offset; regenerate it against $(pin dxmt-source commit)"; exit 1
    fi
    n=$((n + 1))
done
rejects="$(find "$D" -name '*.rej' -o -name '*.orig' | sed -n "1,5p")"
[ -z "$rejects" ] || { echo "::error::patch leftovers: $rejects"; exit 1; }

commit="$(pin dxmt-source commit)"
version="${commit:0:10}-mavrik.$n"
cat > "$SHIM/git" <<EOF
#!/bin/sh
# DXMT's meson asks git describe for its version; the source archive has no .git.
[ "\$1" = describe ] && { echo "$version"; exit 0; }
echo "build-dxmt.sh's stand-in git answers describe only" >&2
exit 1
EOF
chmod +x "$SHIM/git"

# shellcheck disable=SC2046  # the pinned options are one word each
(
    cd "$D"
    export PATH="$SHIM:$VENV/bin:$PATH" MACOSX_DEPLOYMENT_TARGET="$TARGET"
    meson setup "$B" $(pin dxmt-source meson_options) --prefix "$I" \
        -Dnative_llvm_path="$WORK/dxmt-llvm" -Dwine_install_path="$W" \
        -Dc_args="$SRC_MAP" -Dcpp_args="$SRC_MAP" -Dbuild.c_args="$SRC_MAP" -Dbuild.cpp_args="$SRC_MAP"
    meson compile -C "$B"
    meson install -C "$B"
)
mkdir -p "$I/.build"
cp "$D/src/winemetal/unix/winemetal_unix.c" "$I/.build/winemetal_unix.c"
grep -q "\"$version\"" "$B/version.h" || { echo "::error::DXMT's version.h does not say $version"; cat "$B/version.h"; exit 1; }
python3 - "$INPUTS" "$REPO" "$I" "$version" "$VENV" <<'EOF'
import hashlib, json, os, subprocess, sys
inputs, repo, inst, version, venv = sys.argv[1:]
pin = json.load(open(inputs))["inputs"]["dxmt-source"]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
first = lambda cmd: subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0].strip()
patches = sorted(p for p in os.listdir(os.path.join(repo, "dxmt", "patches")) if p.endswith(".patch"))
missing = [f for f in pin["files"] if not os.path.isfile(os.path.join(inst, f))]
if missing:
    sys.exit("DXMT's install lacks " + ", ".join(missing))
record = {
    "commit": pin["commit"],
    "version_string": version,
    "source": {"url": pin["url"], "sha256": pin["sha256"]},
    "patches": [{"file": p, "sha256": sha(os.path.join(repo, "dxmt", "patches", p))} for p in patches],
    "files": {f: sha(os.path.join(inst, f)) for f in pin["files"]},
    "deployment_target": pin["deployment_target"],
    "tools": {"meson": first([os.path.join(venv, "bin", "meson"), "--version"]),
              "ninja": first([os.path.join(venv, "bin", "ninja"), "--version"]),
              "x86_64-w64-mingw32-gcc": first(["x86_64-w64-mingw32-gcc", "--version"]),
              "clang": first(["clang", "--version"])},
}
json.dump(record, open(os.path.join(inst, ".build", "dxmt.json"), "w"), indent=2)
print(json.dumps(record, indent=2))
EOF
rm -rf "$SRC_ROOT" "$B" "$W" "$SHIM"
echo "$dxmt_key" > "$I/.stamp"
echo "::endgroup::"
