# mavrik-engine

The Wine engine for mavrik, a Mac launcher for Windows games. This repository
is the recipe: pinned inputs, a small patch series, and a GitHub workflow that builds the engine,
checks it, and packs it as one archive.

## What it is

This is a build of Wine from CodeWeavers' published CrossOver sources. It is not CrossOver.
"CrossOver" is a trademark of CodeWeavers. CodeWeavers publishes the Wine sources inside each
CrossOver release under the LGPL, and this build uses them as they are, plus the patches in
[`patches/`](patches/).

The engine never presents itself as CrossOver. Patch 0003 gives the Wine loader its own identity
(`org.mavrik.engine`, with each game's own name in its app menu), points Wine's crash dialog at this
repository's issues, and removes CrossOver's names from the places a player could see them. The
`identity` gate checks this on every build.

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
  unpacked into `share/wine`, so a new Windows folder never asks to download them. Wine Mono's
  source archive is an input too: the notices of every project inside Wine Mono come from it.
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
| `build-info.json` | what went in: inputs, patches, the toolchain, the recipe commit and the build run, and the folder layout (`layout`) |

The folder can live anywhere. Every library path inside it is relative, so nothing outside the
folder and macOS is used, and no file names the machine or the folders it was built in.

## For a program that starts the engine

- **GStreamer**: set `GST_REGISTRY_1_0` to a file of the program's own, so GStreamer's plugin list
  is never shared with another GStreamer on the Mac. The plugins are in `lib/gstreamer-1.0`
  (`layout.gstreamer_plugins` in `build-info.json`). GStreamer also finds them there with no
  settings, because they sit beside `libgstreamer`.
- **The game's name**: every Windows program runs as `lib/wine/x86_64-unix/wine`, and each Wine
  process takes its program's name as its bundle name (`ABZU.exe` becomes "ABZU"), so the app menu
  says "Hide ABZU" and "Quit ABZU". `WINEPRELOADERAPPNAME`, set in the environment of the first
  process, replaces that name, up to 32 characters. The Dock and the app switcher show the loader's
  file name, `wine`: LaunchServices names a program without an app bundle after its executable.
- **32-bit programs**: the program that starts the engine sets `WINEARCH=wow64`. Wine's own loader
  then runs a 32-bit program in the process it starts, like a 64-bit one, in new WoW64 mode; the
  engine has no 32-bit Unix side. With `WINEARCH` unset or `win64`, Wine relaunches each 32-bit
  program through `start.exe`, a second process.
- **Identity**: every Wine process reports the bundle identifier `org.mavrik.engine`, so its
  preferences and saved window state are its own, never CrossOver's or another Wine's. The loader is
  not code-signed.
- **Crash dialog**: when a Windows program crashes, Wine shows its crash dialog, which links to this
  repository's issues. A program that does not want players to see it sets the registry value
  `HKCU\Software\Wine\WineDbg\ShowCrashDialog` to 0 in each Windows folder.

## Checks

The build fails unless every gate passes, and a self-test step shows each gate failing on a bad
input, for that gate's own reason (every problem the gate reports on a bad input must be about the
property the case breaks):

- **relocatable**: every Mach-O file is swept with `otool`; no path outside `/usr/lib` and `/System`
  may be absolute.
- **dlopen**: every bundled library loads on the build machine with the build's own folders moved
  away, and nothing loads from outside the engine and macOS.
- **pe32**: the 32-bit Windows half is there (`i386-windows/ntdll.dll` is a 32-bit PE).
- **winemac**: `winemac.so` exports `macdrv_functions` with the layout DXMT reads.
- **addons**: Wine Mono and Gecko are present at exactly the versions the tree asks for; the build
  stops early if the tree asks for a version that is not pinned.
- **wine**: `wine --version` prints the expected version; `wineboot --init` in a new Windows
  folder finishes with no Mono or Gecko download prompt and finds the engine's Mono; and Wine Gecko
  loads from the engine in both the 64-bit and the 32-bit half. Then a small Windows program
  ([`tools/winelibs.c`](tools/winelibs.c)), run in both halves, makes Wine's own code use GnuTLS
  (bcrypt and schannel), MoltenVK and FreeType, and load its GStreamer and FFmpeg modules. dyld
  lists what every Wine process loads: each library Wine opens by name must come from the engine,
  and nothing may come from outside the engine and macOS. This matters on GitHub's Intel runner,
  where Homebrew's libraries sit in a folder dyld searches by default.
- **media**: GStreamer and FFmpeg load from inside the engine, never from
  `/Library/Frameworks/GStreamer.framework`, and create the elements Wine uses. On a Mac that has
  that framework, the gate leaves it in place and checks that nothing is loaded from it.
- **licences**: every file in the engine is covered by a line in `licences/FILES.tsv`.
- **nogpl**: no GPL-only file in the media component, and FFmpeg reports itself as LGPL.
- **identity**: the loader's built-in Info.plist has the engine's own identifier, and no text in
  Wine's files names CrossOver or CodeWeavers, except a reviewed list of names no player sees
  (copyright lines, log lines, internal registry keys), each with its reason, in `gates.py`.
- **buildpaths**: no file in the engine contains the build's work folder or the recipe's folder.
- **d3d11**: a small Windows program ([`tools/d3d11probe.c`](tools/d3d11probe.c)) draws through
  Direct3D 11 on a visible window, as a game does: DXMT's device, 60 frames presented into its Metal
  view, and a texture read back from the GPU. DXMT's `winemetal.so` and the Mac driver load from the
  engine. A machine with no Metal device cannot run DXMT, and the gate reports SKIP there, never
  PASS. GitHub's Intel runners are virtual machines that may have none.
- **playback**: a small Windows program ([`tools/mediaprobe.c`](tools/mediaprobe.c)) decodes a
  one-second movie ([`tools/media/sample.mp4`](tools/media/), H.264 and AAC) in both halves, through
  Media Foundation and through the Windows Media reader, the two ways games play video. GStreamer's
  plugins load from the engine's `lib/gstreamer-1.0`, and nothing from outside the engine and macOS.

## Build notes

- Releases are built on GitHub's `macos-15-intel` runner. The Unix side is x86_64 only: the tree's
  Metal layer is built only for x86_64, as in CrossOver's own builds. It runs under Rosetta on
  Apple silicon. On an Apple silicon Mac, every `configure` and `make` runs as x86_64 through
  Rosetta, and the compilers are told `-arch x86_64`, so the build matches an Intel Mac's. SDL2's
  CMake build is the exception: CMake runs natively and compiles for x86_64.
- The toolchain is part of the recipe. Every step uses the Xcode `inputs.json` pins (26.2, build
  17C52; `scripts/toolchain.sh` selects it, and GitHub's runner has it at `/Applications/Xcode_26.2.app`),
  because the loader's SDK decides which AppKit behaviours a game's windows get. mingw-w64 gcc,
  bison, flex and CMake come from Homebrew; their versions are part of the cache keys and recorded
  in `build-info.json`, so engines built with different tools can be told apart.
- Every compiler gets `-ffile-prefix-map`, our own libraries are stripped like Wine's Unix side, and
  GnuTLS's system-wide priority file is turned off, so no file names the build machine's folders
  and GnuTLS reads no configuration from outside the engine.
- Each library built here keeps the notices of the third-party code inside it (for example
  CRYPTOGAMS and inih in GnuTLS, the BDF and PCF drivers in FreeType, HIDAPI in SDL2). The build
  stops on any licence file in a source tree it has not been told about.
- The Windows side is built for i386 and x86_64 with mingw-w64 gcc. llvm-mingw is known to break
  Steam's sign-in.
- `--with-opengl` is not passed: configure would then fail on the missing EGL headers. Left alone,
  the Mac driver uses OpenGL.framework.
- Wine opens MoltenVK, FreeType, GnuTLS and SDL2 by file name. Each Unix module gets the run path
  `@loader_path/../../`, which is the engine's `lib/`, so those names are found there. The `wine`
  gate checks that they are.
- The Windows side is stripped of debug data; gcc leaves it in, and it makes the files five times
  larger.
- Caches (downloads, the Unix libraries, the Wine build and ccache) make repeat builds fast. Each
  finished step leaves a stamp with its cache key (inputs, scripts, patches and toolchain), and a
  later build with the same key skips it.
  The workflow's `fresh` option (or `FRESH=1` on a Mac) ignores them for a clean build. A step's
  scratch folders (the library sources, the Wine build tree and its objects) are removed when the
  step succeeds; ccache keeps the next build fast.
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
- **On a Mac**: install Xcode 26.2, and with Homebrew bison, mingw-w64, cmake and pkg-config. Apple
  silicon also needs Rosetta. `JOBS` sets make's parallel jobs. Without curl, set
  `FETCH_ARGS="--via gh --from DIR"`: files on GitHub then come through the GitHub CLI, and the rest
  from `DIR`, a folder of files downloaded by hand from the addresses in `inputs.json`. Every file is
  checked against its pin either way.

An engine built on a Mac is for testing only. Releases come only from the GitHub workflow.

## Releases

A run started with `publish_release` publishes a prerelease after every gate and the self-test
pass. It carries the engine, its `.sha256`, the gate results and the source of every LGPL and MPL
part:

- Wine (the CrossOver source archive, with this repository's patches in the recipe), GnuTLS,
  Nettle and GMP, Wine Mono and Wine Gecko;
- DXMT, whose `winemetal.dll` carries Wine's start-up code;
- for the media component, the exact tarballs GStreamer's build recipes (cerbero 1.28.6) built it
  from (GStreamer and its plugin sets, GLib, FFmpeg, proxy-libintl and mpg123), with the sha256
  values cerbero pins, and cerbero itself, which holds the patches it applied.

Those sources are in `release_sources` in `inputs.json` (or are inputs with the role `source`). A
release refuses to start while any of them has no pinned size and sha256. A test build downloads
the ones it can and prints the values to pin. On a Mac whose build takes files from a folder
(`--from DIR`), `scripts/fetch-release-sources.sh DIR` downloads the ones that are not on GitHub,
checks them against their pins and prints the values still to pin.

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
