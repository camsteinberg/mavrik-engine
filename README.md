# mavrik-engine

The Wine engine for mavrik, a Mac launcher for Windows games. This repository
is the recipe: pinned inputs, a small patch series, and a GitHub workflow that builds the engine,
checks it, and packs it as one archive.

## What it is

This is a build of Wine from CodeWeavers' published CrossOver sources. It is not CrossOver.
"CrossOver" is a trademark of CodeWeavers. CodeWeavers publishes the Wine sources inside each
CrossOver release under the LGPL, and this build uses them as they are, plus the patches in
[`patches/`](patches/).

## Bugs

A game that misbehaves on this engine is a bug for this repository. Please open an issue here.
Never report it to CodeWeavers or to WineHQ: this is a patched build, and their bug trackers are
for their own releases.

## What it builds from

Every input is pinned by its address, size and SHA-256 in [`inputs.json`](inputs.json). A release
build refuses any input without a pinned hash.

- **Wine**: CodeWeavers' CrossOver 26.3.0 sources (Wine 11.0), `sources/wine` in the archive.
- **Patches**: [`patches/`](patches/), applied in order. [`patches/README.md`](patches/README.md)
  says why each one is there.
- **Wine Mono and Wine Gecko**: the versions the Wine tree asks for (`dlls/appwiz.cpl/addons.c`),
  unpacked into `share/wine`, so a new Windows folder never asks to download them.
- **MoltenVK**: Vulkan on Metal, from Khronos' own release.
- **DXMT v0.80**: Direct3D 10 and 11 on Metal. Its 64-bit files go into Wine's own folders, the
  way mavrik has tested them.
- **Media**: GStreamer and FFmpeg from GStreamer's official macOS packages, LGPL parts only, with no
  GPL file. They sit inside the engine, so the engine never uses a GStreamer.framework installed on
  the Mac.
- **Unix libraries**: GnuTLS (with Nettle and GMP), FreeType and SDL2, built here from their source
  releases.

D3DMetal (Apple's Game Porting Toolkit) is never part of this build or downloaded by it. The
CrossOver tree can host it; a player's copy is installed separately under Apple's licence.

## The engine archive

`mavrik-engine-<wine version>-cx<CrossOver sources version>-r<revision>.tar.xz` holds one folder:

| Path | What it holds |
|---|---|
| `bin/` | `wine` and `wineserver` |
| `lib/wine/` | Wine's Windows side (`i386-windows`, `x86_64-windows`) and Unix side (`x86_64-unix`) |
| `lib/` | the Unix libraries Wine opens, MoltenVK and the media libraries, flat |
| `lib/gstreamer-1.0/` | the GStreamer plugins |
| `share/wine/` | Wine's data, Wine Mono and Wine Gecko |
| `licences/` | every part's licence and notices; `FILES.tsv` names the part every file belongs to |
| `build-info.json` | what went in: inputs, patches, the recipe commit and the build run |

The folder can live anywhere. Every library path inside it is relative, so nothing outside the
folder and macOS is used. A program that starts the engine should set `GST_REGISTRY_1_0` to a
file of its own, so GStreamer's plugin list is never shared with another GStreamer.

## Checks

The build fails unless every gate passes, and a self-test step shows each gate failing on a bad
input:

- **relocatable**: every Mach-O file is swept with `otool`; no path outside `/usr/lib` and `/System`
  may be absolute.
- **dlopen**: every bundled library loads on the build machine with the build's own folders moved
  away, and nothing loads from outside the engine and macOS.
- **pe32**: the 32-bit Windows half is there (`i386-windows/ntdll.dll` is a 32-bit PE).
- **winemac**: `winemac.so` exports `macdrv_functions` with the layout DXMT reads.
- **addons**: Wine Mono and Gecko are present at exactly the versions the tree asks for; the build
  stops early if the tree asks for a version that is not pinned.
- **wine**: `wine --version` prints the expected version, and `wineboot --init` in a new Windows
  folder finishes with no Mono or Gecko download prompt.
- **media**: GStreamer and FFmpeg load from inside the engine, never from
  `/Library/Frameworks/GStreamer.framework`, and create the elements Wine uses. On a Mac that has
  that framework, the gate leaves it in place and checks that nothing is loaded from it.
- **licences**: every file in the engine is covered by a line in `licences/FILES.tsv`.
- **nogpl**: no GPL-only file in the media component, and FFmpeg reports itself as LGPL.

## Build notes

- Releases are built on GitHub's `macos-15-intel` runner. The Unix side is x86_64 only: the tree's
  Metal layer is built only for x86_64, as in CrossOver's own builds. It runs under Rosetta on
  Apple silicon. On an Apple silicon Mac, every configure and make runs as x86_64 through Rosetta,
  and the compilers are told `-arch x86_64`, so the build matches an Intel Mac's.
- The Windows side is built for i386 and x86_64 with mingw-w64 gcc. llvm-mingw is known to break
  Steam's sign-in.
- `--with-opengl` is not passed: configure would then fail on the missing EGL headers. Left alone,
  the Mac driver uses OpenGL.framework.
- Wine opens MoltenVK, FreeType, GnuTLS and SDL2 by file name. Each Unix module gets the run path
  `@loader_path/../../`, which is the engine's `lib/`, so those names are found there.
- The Windows side is stripped of debug data; gcc leaves it in, and it makes the files five times
  larger.
- Caches (downloads, the Unix libraries, the Wine build and ccache) make repeat builds fast. Each
  finished step leaves a stamp with its cache key, and a later build with the same key skips it.
  The workflow's `fresh` option (or `FRESH=1` on a Mac) ignores them for a clean build.
- `MACOSX_DEPLOYMENT_TARGET` is 14.0 for everything built here. DXMT v0.80's own files need
  macOS 15.

## Building

The build is four scripts in [`scripts/`](scripts/). The GitHub workflow prepares its runner and
calls them, and a Mac runs the very same scripts:

```sh
bash scripts/build.sh WORK      # inputs, toolchain check, sources and patches, Unix libraries, Wine
bash scripts/assemble.sh WORK   # the engine folder, its build record and its licence folder
bash scripts/gates.sh WORK      # every gate, then the self-test
bash scripts/pack.sh WORK       # the .tar.xz and its .sha256
```

- **On GitHub**: start the `build` workflow by hand (Actions, build, Run workflow). The engine, its
  checksum and the gate results are uploaded as the run's artifact.
- **On a Mac**: install Xcode, and with Homebrew bison, mingw-w64, cmake and pkg-config. Apple
  silicon also needs Rosetta. `JOBS` sets make's parallel jobs. Without curl, set
  `FETCH_ARGS="--via gh --from DIR"`: files on GitHub then come through the GitHub CLI, and the rest
  from `DIR`, a folder of files downloaded by hand from the addresses in `inputs.json`. Every file is
  checked against its pin either way.

An engine built on a Mac is for testing only. Releases come only from the GitHub workflow.

## Releases

A run started with `publish_release` publishes a prerelease after every gate and the self-test
pass. It carries the engine, its `.sha256`, the gate results and the source of every LGPL and MPL
part. The release step refuses to run while any of those sources is not pinned.

## Credits

- CodeWeavers, for CrossOver and for publishing its Wine sources, and the Wine project.
- [highball-engine](https://github.com/gauthierpiarrette/highball-engine) (LGPL-2.1-or-later): the
  closest recipe to this one. Patches 0001 and 0002 come from it unchanged, and the build follows
  its shape (pinned CrossOver sources, an Intel runner, mingw-w64 gcc, Mono and Gecko unpacked).
- [winecx-gptk](https://github.com/frankea/winecx-gptk), whose list of build gates showed which
  checks a shipped engine needs. Nothing is copied from it.
- Gcenx, whose macOS Wine builds showed the configure options and the libraries a Mac engine needs.
- The DXMT, MoltenVK, GStreamer, FFmpeg, GnuTLS, FreeType and SDL authors.
- The media component's script started as mavrik's own `make-media-component.sh`.

## Licence

The recipe, the scripts and the patches are LGPL-2.1-or-later ([LICENSE](LICENSE)), like Wine.
[NOTICE.md](NOTICE.md) lists every part the engine carries, where it comes from and its licence.
Inside each engine, `licences/` holds the full licence texts and copyright notices.
