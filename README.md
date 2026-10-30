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
- **DXMT** (main at 3b252590cb, 2026-10-27; no release has followed v0.80): Direct3D 10 and 11 on
  Metal, built here from its source with this repository's patches in [`dxmt/patches/`](dxmt/README.md)
  (`scripts/build-dxmt.sh`, as DXMT's own CI job builds it: LLVM 15.0.7, 3Shain's Wine 8.16, meson and
  mingw-w64, every input pinned and mirrored on this repository's releases). Patch 0001 counts DXMT's
  frame latency to presentation under vsync, as DXVK and Windows do. Its 64-bit files go into Wine's
  own folders, the way mavrik has tested them.
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
  process, replaces that name, and every process it starts keeps it, so a game whose launcher starts
  the real game keeps its name. The name has 32 bytes: the loader writes it into its Info.plist with
  `&`, `<` and `>` escaped (an escaped `&` takes 5 bytes, an accented or CJK character 2 or 3, an
  emoji 4) and cuts it only between whole characters. The menu bar, Cmd-Tab, the Dock and the app
  switcher show the same name (patch 0007): each program starts through a symbolic link to the loader
  named after it, in `winetemp-<loader's inode, size and time>/` in the user's temp folder (macOS's
  window server takes a program's name only from the file it was started through). The window server
  keeps the name decomposed (NFD), at most 31 bytes of it, so the link's name is cut between whole
  characters where its decomposed form fits 31 bytes (an accent or a katakana voicing mark takes 3 more
  bytes, a Korean syllable 9), with `/` shown as `∕` (U+2215) and control characters dropped. The process's executable is still the loader inside the engine (`proc_pidpath`), so a
  program can find the engine's processes by their path. When no link can be made, the Mac driver
  still names the process in the Dock and the app switcher with a private LaunchServices call (patch
  0006), looked up at run time; the menu bar then shows `wine`.
- **Sound**: Wine sets the Mac output device's buffer frame size to its own period when a stream starts, and
  reports the device's real period (512 frames at 48 kHz, 10.67 ms) to games (patch 0009, upstream Wine's).
- **Full screen**: a game's always-on-top full-screen window drops to the normal window level while
  the engine is not the active app (patch 0008), so Cmd-Tab can leave a full-screen game. Other
  always-on-top windows stay above the Dock, as in Wine. While a game's window covers a whole screen and
  the engine is the active app, the Dock and the menu bar are hidden (patch 0034), so the Dock doesn't
  wake at the screen's edge under the game.
- **The mouse cursor**: a cursor a Windows program hides is a transparent Mac cursor, set again after
  another app was in front and whenever the pointer comes back from another app's window, so the Mac
  arrow doesn't come back over a full-screen game after Cmd-Tab, at the Dock edge or on shake to locate
  (patches 0013, Wine merge request 11880, and 0014, this repository's follow-up to it). In Mission
  Control and App Exposé, which leave the game the active app, a cursor clip lets the pointer go: while a
  game clips, the Mac driver reads the window list every 100 ms for WindowManager's full-display window at
  layer 19 (what those two overlays draw on macOS 27), lifts the clip while it shows, and puts the clip and
  the hidden cursor back when it goes (patch 0015).
- **A per-launch DLL folder**: `WINEDLLPATH_PREPEND` names folders searched before the engine's own
  builtins (patch 0018, MacPorts' and Highball's), so a launcher can put another graphics layer, such
  as Apple's D3DMetal, in front of DXMT for one game.
- **Fixes from Highball's engine** (patches 0019 to 0033, each with its own header): the fiber and
  error-code slots macOS shares with Windows code (fiber games, Unity's error codes), Unity and
  Unreal videos under DXMT, old modules no longer turning data execution prevention off for a whole
  process under Rosetta, missing GetIntegratedDisplaySize, a process's memory figures, Keychain
  credentials, Retina screen sizes, OpenGL ES 2 calls, spatial audio channel order, app packages,
  UTC+3 time zone names, and DLLs kept in a program's `<program>.exe.local` folder.
- **32-bit programs**: the program that starts the engine sets `WINEARCH=wow64`. Wine's own loader
  then runs a 32-bit program in the process it starts, like a 64-bit one, in new WoW64 mode; the
  engine has no 32-bit Unix side. With `WINEARCH` unset or `win64`, Wine relaunches each 32-bit
  program through `start.exe`, a second process.
- **Steam bridge**: when a game loads Valve's `steamclient.dll` or `steamclient64.dll`, the loader
  makes its calls go to `lsteamclient.dll` (patch 0004), which talks to the Mac Steam app. lsteamclient
  is not in this engine; it is built from Valve's Proton source as its own archive
  ([`bridge/`](bridge/README.md)), and a program that starts the engine adds its `lib/wine` files to
  the engine's `lib/wine`. The redirect is on unless
  `PROTON_DISABLE_LSTEAMCLIENT=1` is set, as in Proton, which always ships lsteamclient. Without
  lsteamclient a 32-bit `steamclient.dll` loads as it is, but `steamclient64.dll` and
  `gameoverlayrenderer64.dll` still have their `tier0_s64.dll` and `vstdlib_s64.dll` imports sent to
  ntdll, which has none of those functions: each becomes a stub that fails when called. So a program
  that runs Valve's own Windows Steam client in this engine, with no lsteamclient, sets
  `PROTON_DISABLE_LSTEAMCLIENT=1`, the switch Proton's players use as a launch option.
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
- **dxmt**: DXMT's seven files are the ones `build-dxmt.sh` made from the pinned source and this
  repository's DXMT patches (the build record, file by file); `d3d11.dll` carries the version string
  `<commit>-mavrik.<patches>`; `winemetal.dll` exports the pinned number of names, with patch 0002's
  `MetalDrawable_signalEventWhenPresented`, which `d3d11.dll` imports; `winemetal.so` needs macOS 15.0;
  none of the seven names the work folder, the recipe or the home folder.
- **d3d11**: a small Windows program ([`tools/d3d11probe.c`](tools/d3d11probe.c)) draws through
  Direct3D 11 on a visible window, as a game does: DXMT's device, 60 frames presented into its Metal
  view, 120 more under vsync at 50 or more a second with no presentation wait given up (DXMT patch
  0001), and a texture read back from the GPU. DXMT's `winemetal.so` and the Mac driver load from the
  engine. A machine with no Metal device cannot run DXMT, and the gate reports SKIP there, never
  PASS. GitHub's Intel runners are virtual machines that may have none.
- **playback**: a small Windows program ([`tools/mediaprobe.c`](tools/mediaprobe.c)) decodes a
  one-second movie ([`tools/media/sample.mp4`](tools/media/), H.264 and AAC) in both halves, through
  Media Foundation and through the Windows Media reader, the two ways games play video. GStreamer's
  plugins load from the engine's `lib/gstreamer-1.0`, and nothing from outside the engine and macOS.
- **steamredirect**: Valve's Steam bridge in the loader (patch 0004). A small Windows program
  ([`tools/steamprobe.c`](tools/steamprobe.c)), in both halves, loads a DLL named `steamclient64.dll`
  or `steamclient.dll` with a stand-in `lsteamclient.dll` beside it, and calls an export: the call
  must land in lsteamclient's export of the same name. No Steam is needed.
- **dockname**: a small Windows program ([`tools/dockprobe.c`](tools/dockprobe.c)) started with
  `WINEPRELOADERAPPNAME` shows a window and starts a 32-bit copy of itself that shows its own. For
  both, the Dock and the app switcher (LaunchServices, read with `lsappinfo`) and the menu bar and
  Cmd-Tab (the window server's owner name, read with [`tools/procnames.c`](tools/procnames.c), no
  screen capture) must show that name exactly, for three titles: a plain one, one with `&`, `<` and
  `>`, and one with accented, CJK and emoji characters (the window server's name compared in its
  decomposed form, as macOS keeps it). Three more titles show the rules: a Japanese title of 36 bytes
  is cut between whole characters (to 30 bytes in the Dock, to 27 in the window server, where its
  "ゲ" decomposes to 6), `AC/DC Gate` shows as `AC∕DC Gate` in the window server, and `Control` still starts the probe, not Wine's control panel. Each
  program's executable (`proc_pidpath`) must be the loader inside the engine. A title no link can carry
  (`..`) must still reach the Dock through patch 0006. With no title and an argv[0] that is not UTF-8,
  the program must still start (no link, so the window server keeps `wine`) and its 32-bit child keeps
  its own name. The executable path is checked as `proc_pidpath` gives it, without resolving links. Only probes started by the gate's own run are
  read, and the gate removes the links it caused. When the gates run outside a login session
  (`launchctl managername` is not `Aqua`, as over ssh) no window can become a Dock app, and the gate
  reports SKIP; inside one, it runs and passes or fails. Two self-test rows need revision 4's
  `ntdll.so` (CrossOver's hack as shipped), named in `SELFTEST_OLD_NTDLL`; without it they are not run.

## Build notes

- Releases are built on GitHub's `macos-15-intel` runner. The Unix side is x86_64 only: the tree's
  Metal layer is built only for x86_64, as in CrossOver's own builds. It runs under Rosetta on
  Apple silicon. On an Apple silicon Mac, every `configure` and `make` runs as x86_64 through
  Rosetta, and the compilers are told `-arch x86_64`, so the build matches an Intel Mac's. The SDL3
  and sdl2-compat CMake builds are the exception: CMake runs natively and compiles for x86_64.
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

Releases are meant to come from the GitHub workflow, which has not built one yet. Until it does,
prereleases are built on a Mac by these same scripts and checked by the same gates and self-test:
revisions 3 to 6 were, and their release notes say so. Any other engine built on a Mac is for testing
only.

## Releases

A run started with `publish_release` publishes a prerelease after every gate and the self-test
pass. A dockname SKIP is not a pass for a release: if the runner reports SKIP, the prerelease is not
published until the same recipe commit has passed dockname on a Mac in a login session, and that
run's `gates/results.json` goes with the release's gate results. The workflow does not enforce this
yet; whoever starts the release checks it. A release carries the engine, its `.sha256`, the gate
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

## Credits

- CodeWeavers, for CrossOver and for publishing its Wine sources, and the Wine project.
- [highball-engine](https://github.com/gauthierpiarrette/highball-engine) (LGPL-2.1-or-later): the
  closest recipe to this one. Patches 0001, 0002, 0010 (its MSync fix) and 0018 to 0032 come from it unchanged, with
  the authors each one's header names (Gauthier Piarrette, athei, Tx, Paul Gofman and Proton's developers, and
  MacPorts' game-porting-toolkit port for 0018), and the build follows
  its shape (pinned CrossOver sources, an Intel runner, mingw-w64 gcc, Mono and Gecko unpacked).
- [winecx-gptk](https://github.com/frankea/winecx-gptk), whose list of build gates showed which
  checks a shipped engine needs. Nothing is copied from it.
- Gcenx, whose macOS Wine builds showed the configure options and the libraries a Mac engine needs.
- Valve, for Proton's Steam bridge: patches 0004 and 0005 are Valve's loader change and makedep line
  from ValveSoftware/wine (`proton_11.0`), ported to this tree.
- [NotProton](https://github.com/NotProtonNot/NotProton), which showed Valve's bridge working on a Mac
  with the Mac Steam app. Nothing is copied from it.
- Chromium, Firefox and WebKit, whose way of naming a process in the Dock patch 0006 follows.
- Wine's developers, whose commits patches 0009, 0011 and 0012 carry unchanged (Zhiyi Zhang's Core Audio
  period fix and Giovanni Mascellani's guard; Esme Povirk's Wine Mono updates; Alexandre Julliard's FAudio
  imports and Alex Henrie's FAudio fix).
- Elvin Hayatov, whose Wine merge request 11880 patch 0013 carries (the transparent hidden cursor).
- CodeWeavers' CW HACK 22144, which patch 0007 adapts: CrossOver already starts each Windows program
  through a link named after it.
- The DXMT, MoltenVK, GStreamer, FFmpeg, GnuTLS, FreeType and SDL authors, and the Liberation fonts'
  designers (Ascender, Steve Matteson, Red Hat). Proton, whose Windows font names 0017 follows.
- The media component's script started as mavrik's own `make-media-component.sh`.

## Licence

The recipe, the scripts and the patches are LGPL-2.1-or-later ([LICENSE](LICENSE)), like Wine,
except `bridge/patches/0002` (Steamworks SDK licence) and `0003` (BSD-3-Clause); see
[bridge/README.md](bridge/README.md#licence).
[NOTICE.md](NOTICE.md) lists every part the engine carries, where it comes from and its licence.
Inside each engine, `licences/` holds the full licence texts and copyright notices.
