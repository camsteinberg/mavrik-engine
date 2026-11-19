# Gates

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
  ([`tools/winelibs.c`](../tools/winelibs.c)), run in both halves, makes Wine's own code use GnuTLS
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
- **d3d11**: a small Windows program ([`tools/d3d11probe.c`](../tools/d3d11probe.c)) draws through
  Direct3D 11 on a visible window, as a game does: DXMT's device, 60 frames presented into its Metal
  view, 120 more under vsync at 50 or more a second with no presentation wait given up (DXMT patch
  0001), and a texture read back from the GPU. DXMT's `winemetal.so` and the Mac driver load from the
  engine. A machine with no Metal device cannot run DXMT, and the gate reports SKIP there, never
  PASS. GitHub's Intel runners are virtual machines that may have none.
- **playback**: a small Windows program ([`tools/mediaprobe.c`](../tools/mediaprobe.c)) decodes a
  one-second movie ([`tools/media/sample.mp4`](../tools/media/), H.264 and AAC) in both halves, through
  Media Foundation and through the Windows Media reader, the two ways games play video. GStreamer's
  plugins load from the engine's `lib/gstreamer-1.0`, and nothing from outside the engine and macOS.
- **steamredirect**: Valve's Steam bridge in the loader (patch 0004). A small Windows program
  ([`tools/steamprobe.c`](../tools/steamprobe.c)), in both halves, loads a DLL named `steamclient64.dll`
  or `steamclient.dll` with a stand-in `lsteamclient.dll` beside it, and calls an export: the call
  must land in lsteamclient's export of the same name. No Steam is needed.
- **dockname**: a small Windows program ([`tools/dockprobe.c`](../tools/dockprobe.c)) started with
  `WINEPRELOADERAPPNAME` shows a window and starts a 32-bit copy of itself that shows its own. For
  both, the Dock and the app switcher (LaunchServices, read with `lsappinfo`) and the menu bar and
  Cmd-Tab (the window server's owner name, read with [`tools/procnames.c`](../tools/procnames.c), no
  screen capture) must show that name exactly, for three titles: a plain one, one with `&`, `<` and
  `>`, and one with accented, CJK and emoji characters (the window server's name compared in its
  decomposed form, as macOS keeps it). Three more titles show the rules: a Japanese title of 36 bytes
  is cut between whole characters (to 30 bytes in the Dock, to 27 in the window server, where its
  "ゲ" decomposes to 6), `AC/DC Gate` shows as `AC∕DC Gate` in the window server, and `Control` still starts the probe, not Wine's control panel. Each
  program's executable (`proc_pidpath`) must be the loader in the engine's `mavrik.app` (patch 0037); with
  `MAVRIK_GAME_MODE=0`, the plain title shows the same and the executable is the loader in
  `without-game-mode/mavrik.app`. A title no link can carry (`..`) shows the bundle's name, `mavrik`, everywhere.
  With no title and an argv[0] that is not UTF-8, the program must still start, and each program shows its own
  file's name in both sources (patch 0007 names the first link after the program, not after argv[0]). On an APFS
  clone of the engine with a plain file where its loader's link folder goes, so no link can be made, a program with
  no title and its child show `mavrik`, never `wine`. The executable path is checked as `proc_pidpath` gives it,
  without resolving links. Only probes started by the gate's own run are
  read, and the gate removes the links it caused. When the gates run outside a login session
  (`launchctl managername` is not `Aqua`, as over ssh) no window can become a Dock app, and the gate
  reports SKIP; inside one, it runs and passes or fails. Two self-test rows need this revision's
  `ntdll.so` without patch 0007 (CrossOver's hack as shipped), named in `SELFTEST_OLD_NTDLL`, and one needs
  revision 11's `ntdll.so`, named in `SELFTEST_R11_NTDLL`; without them they are not run.
- **controllers**: game controllers through patch 0035's scripted virtual pad, with no real pad.
  [`tools/gamepadprobe.c`](../tools/gamepadprobe.c) (neutron's probe) runs its selftest in a fresh Windows
  folder, each case in its own Wine session (the pad's variables count when the session starts), with
  the virtual pad as an Xbox 360 pad (045e:028e), a DualShock 4 (054c:09cc), a DualSense (054c:0ce6)
  and a Switch Pro Controller (057e:2009, by position), in both halves: all 18 checks must pass
  (XInput buttons and axes, rumble echoed, still held after 1.5 s and stopped, the wired battery,
  DirectInput, raw input, Windows.Gaming.Input, unplug, replug and input after it). With
  `MAVRIK_PAD_HIDRAW=1`, each PlayStation id must be no XInput pad and no DirectInput controller. The
  self-test breaks one property each: a DualShock 4 with `MAVRIK_PAD_HIDRAW=1` in the full selftest, the
  same id in the absent check without it, and a Switch Pro Controller with SDL's label mapping back on.
- **gamemode**: the two loader bundles (patch 0037), `lib/wine/x86_64-unix/mavrik.app` and
  `lib/wine/x86_64-unix/without-game-mode/mavrik.app`, have exactly the Info.plists `scripts/assemble.py` writes (the
  first the games category, `LSSupportsGameMode` and `GCSupportsGameMode`; the second none of them and its own
  identifier; both `LSUIElement`, `CFBundleName` `mavrik`, `CFBundleExecutable` `wine`, the Local Network usage
  text, no document types); each `Contents/MacOS/wine` is the engine's loader with a signature added; and each ad
  hoc signature verifies (`codesign --verify --strict`), so the Info.plist is sealed. Then the switch, with no
  display: a 64-bit program with no title, its 32-bit child and its 64-bit grandchild
  ([`tools/chainprobe.c`](../tools/chainprobe.c)), run once without `MAVRIK_GAME_MODE` and once with
  `MAVRIK_GAME_MODE=0`, and once with `MAVRIK_GAME_MODE=1` (only exactly `0` turns Game Mode off), must each start
  through a link named after its file in the link folder of the loader in `without-game-mode/mavrik.app` with `0`
  and of the one in `mavrik.app` otherwise, and nowhere else. Each child starts from the loader its parent chose and
  inherits the variable with the rest of the Unix environment, so the grandchild proves it passes through two
  generations. Whether macOS then turns Game Mode on is
  not a gate (it needs a full-screen game in front); the lab reads it from gamepolicyd. One self-test row needs
  revision 11's `ntdll.so` (no switch), named in `SELFTEST_R11_NTDLL`.
