# Building and releasing

The build is four scripts in [`scripts/`](../scripts/). I run them on my Mac, from the repository's
root:

```sh
bash scripts/build.sh WORK      # inputs, toolchain check, sources and patches, Unix libraries, Wine
bash scripts/assemble.sh WORK   # the engine folder, its build record and its licence folder
bash scripts/gates.sh WORK      # every gate, then the self-test
bash scripts/pack.sh WORK       # the .tar.xz and its .sha256
```

- **On a Mac**: install Xcode 26.2, and with Homebrew bison, mingw-w64, cmake and pkg-config. Apple
  silicon also needs Rosetta. `JOBS` sets make's parallel jobs. Without curl, set
  `FETCH_ARGS="--via gh --from DIR"`: files on GitHub then come through the GitHub CLI, and the rest
  from `DIR`, a folder of files downloaded by hand from the addresses in `inputs.json`. Every file is
  checked against its pin either way.
- **On GitHub**: [`.github/workflows/build.yml`](../.github/workflows/build.yml) prepares GitHub's
  `macos-15-intel` runner and calls the same four scripts. It is started by hand (Actions, build, Run
  workflow) and uploads the engine, its checksum and the gate results as the run's artifact. It has
  never completed a run, so treat it as untested.

Every release so far, revisions 3 to 13, was built on my Mac by these scripts and passed every gate
and self-test row the recipe had at the time (13 gates at revision 3, 19 at revision 13). Each release
carries its gate results and its build record.

## Inputs

Every input is pinned by its address, size and SHA-256 in [`inputs.json`](../inputs.json). A release
build refuses any input without a pinned hash.

- **Wine**: CodeWeavers' CrossOver 26.3.0 sources (Wine 11.0), `sources/wine` in the archive.
- **Patches**: [`patches/`](../patches/), applied in order. [`patches/README.md`](../patches/README.md)
  says why each one is there.
- **Wine Mono and Wine Gecko**: the versions the Wine tree asks for (`dlls/appwiz.cpl/addons.c`),
  unpacked into `share/wine`, so a new Windows folder never asks to download them. Wine Mono's
  source archive is an input too: the notices of every project inside Wine Mono come from it.
- **MoltenVK**: Vulkan on Metal, from Khronos' own release.
- **DXMT** (main at 647b0020ba, 2026-11-02; no release has followed v0.80): Direct3D 10 and 11 on
  Metal, built here from its source with this repository's patches in [`dxmt/patches/`](../dxmt/README.md)
  (`scripts/build-dxmt.sh`, as DXMT's own CI job builds it: LLVM 15.0.7, 3Shain's Wine 8.16, meson and
  mingw-w64, every input pinned and mirrored on this repository's releases). Patch 0002 counts DXMT's
  frame latency to presentation under vsync, as DXVK and Windows do. Its 64-bit files go into Wine's
  own folders, the way Mavrik has tested them.
- **Media**: GStreamer and FFmpeg from GStreamer's official macOS packages, LGPL parts only, with no
  GPL file. They sit inside the engine, so the engine never uses a GStreamer.framework installed on
  the Mac.
- **Unix libraries**: GnuTLS (with Nettle and GMP), FreeType, SDL3 and sdl2-compat, built here from
  their source releases. Wine's game controller support (winebus) calls SDL2's interface; sdl2-compat
  gives it on SDL3, SDL's live line (SDL2 stopped at 2.32.10). sdl2-compat opens SDL3 at run time, so
  the engine carries SDL3 as `lib/libSDL3.dylib`, the first name sdl2-compat tries.
- **Fonts**: the Liberation fonts 2.1.5 (Sans, Serif and Mono, metric-compatible with Arial, Times New
  Roman and Courier New), unchanged in `share/wine/fonts`, from their TTF archive mirrored on this
  repository's releases. wine.inf copies them into each Windows folder's `C:\windows\Fonts` under the
  file names Proton uses, never over a file already there (patches 0016 and 0017).

## Build notes

- The Unix side is x86_64 only: the tree's Metal layer is built only for x86_64, as in CrossOver's
  own builds. It runs under Rosetta on Apple silicon. On an Apple silicon Mac, every `configure` and
  `make` runs as x86_64 through Rosetta, and the compilers are told `-arch x86_64`, so the build
  matches an Intel Mac's. The SDL3 and sdl2-compat CMake builds are the exception: CMake runs
  natively and compiles for x86_64.
- The toolchain is part of the recipe. Every step uses the Xcode `inputs.json` pins (26.2, build
  17C52; `scripts/toolchain.sh` selects it, and GitHub's runner has it at `/Applications/Xcode_26.2.app`),
  because the loader's SDK decides which AppKit behaviours a game's windows get. mingw-w64 gcc,
  bison, flex and CMake come from Homebrew; their versions are part of the cache keys and recorded
  in `build-info.json`, so engines built with different tools can be told apart.
- Every compiler gets `-ffile-prefix-map`, our own libraries are stripped like Wine's Unix side, and
  GnuTLS's system-wide priority file is turned off, so no file names the build machine's folders
  and GnuTLS reads no configuration from outside the engine.
- Each library built here keeps the notices of the third-party code inside it (for example
  CRYPTOGAMS and inih in GnuTLS, the BDF and PCF drivers in FreeType, HIDAPI in SDL3). The build
  stops on any licence file in a source tree it has not been told about.
- The Windows side is built for i386 and x86_64 with mingw-w64 gcc. llvm-mingw is known to break
  Steam's sign-in.
- `--with-opengl` is not passed: configure would then fail on the missing EGL headers. Left alone,
  the Mac driver uses OpenGL.framework.
- Wine opens MoltenVK, FreeType, GnuTLS and SDL2 (sdl2-compat) by file name. Each Unix module gets
  the run path `@loader_path/../../`, which is the engine's `lib/`, so those names are found there.
  The `wine` gate checks that they are, and that sdl2-compat's SDL3 loads from the engine too.
- The Windows side is stripped of debug data; gcc leaves it in, and it makes the files five times
  larger.
- Caches (downloads, the Unix libraries, the Wine build and ccache) make repeat builds fast. Each
  finished step leaves a stamp with its cache key (inputs, scripts, patches and toolchain), and a
  later build with the same key skips it.
  The workflow's `fresh` option (or `FRESH=1` on a Mac) ignores them for a clean build. A step's
  scratch folders (the library sources, the Wine build tree and its objects) are removed when the
  step succeeds; ccache keeps the next build fast.
- `MACOSX_DEPLOYMENT_TARGET` is 14.0 for everything built here. DXMT's own files need
  macOS 15.

## Releases

I publish each release by hand once every gate and the self-test pass on my Mac, in a login session,
because the dockname gate needs one.

The workflow can publish too, though it never has: a run started with `publish_release` publishes a
prerelease after every gate and the self-test pass. A dockname SKIP is not a pass for a release: if the runner reports SKIP, the prerelease is not
published until the same recipe commit has passed dockname on a Mac in a login session, and that
run's `gates/results.json` goes with the release's gate results. The workflow does not enforce this
yet, so it has to be checked by hand. A release carries the engine, its `.sha256`, the gate
results and the source of every LGPL and MPL part:

- Wine (the CrossOver source archive, with this repository's patches in the recipe), GnuTLS,
  Nettle and GMP, Wine Mono and Wine Gecko;
- DXMT, complete with its submodules (GitHub's tarball of a commit leaves them empty), with this
  repository's DXMT patches in the recipe, and the source
  of Wine's start-up code its `winemetal.dll` carries (winecrt0 and its headers, from 3Shain's Wine 8.16;
  `dxmt/README.md`);
- for the media component, the exact tarballs GStreamer's build recipes (cerbero 1.28.8) built it
  from (GStreamer and its plugin sets, GLib, FFmpeg, proxy-libintl and mpg123), with the sha256
  values cerbero pins, and cerbero itself, which holds the patches it applied.

Those sources are in `release_sources` in `inputs.json` (or are inputs with the role `source`). A
release refuses to start while any of them has no pinned size and sha256. A test build downloads
the ones it can and prints the values to pin. On a Mac whose build takes files from a folder
(`--from DIR`), `scripts/fetch-release-sources.sh DIR` downloads the ones that are not on GitHub,
checks them against their pins and prints the values still to pin.
