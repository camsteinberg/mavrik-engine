# Using the engine from a launcher

What is inside an engine archive, and what a program that starts it can set. Mavrik is the launcher
this was written for, but any program that starts the engine can use the same switches.

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

## What a launcher can set

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
  program can find the engine's processes by their path. With no `WINEPRELOADERAPPNAME`, the first program's
  link is named after the program on the command line, not after `wine` (patch 0007, revision 12), and each
  child's after its own file. When no link can be made, the program starts from the loader in `mavrik.app`
  itself, and every surface shows the bundle's name, `mavrik` (patch 0037); never `wine`.
- **Sound**: Wine sets the Mac output device's buffer frame size to its own period when a stream starts, and
  reports the device's real period (512 frames at 48 kHz, 10.67 ms) to games (patch 0009, upstream Wine's),
  counted in the device's frames when the stream's rate differs (patch 0038). The 32-bit Windows half is
  built with Proton's i386 flags (`-mstackrealign -march=nocona -mfpmath=sse`), so its float math, such as
  DirectSound's resampler, is SSE, not the x87 code Rosetta runs slowly. The default sound device a game sees, "System Default Output", follows
  the Mac's default output while the game plays (AirPods connecting, or a device going away), and a stream a game opens
  on a named device stays there, as on Windows (patch 0043).
- **Full screen**: a game's always-on-top full-screen window drops to the normal window level while
  the engine is not the active app (patch 0008), so Cmd-Tab can leave a full-screen game. Other
  always-on-top windows stay above the Dock, as in Wine. While a game's window covers a whole screen and
  the engine is the active app, the Dock and the menu bar are hidden (patch 0034), so the Dock doesn't
  wake at the screen's edge under the game.
- **Fit below the notch**: with the Mac driver option `FitBelowNotch=y` (off by default), a game sees each
  screen with a camera housing without the strip beside it (1512x945 on a 14-inch MacBook Pro), its
  smaller modes scaled into that area, and a full-screen game gets a black strip beside the housing, as
  VLC and QuickTime Player do (patch 0040).
- **Display mode changes**: when the Mac's display mode changes while a game plays (System Settings' "Larger
  Text", another app), the game's windows refit the new screen: a full-screen game fills it and a windowed one scales
  with the screen, as a graphics card's scaler shows a mode on another panel. The game keeps its own mode and is told
  nothing, so it resets nothing; on the way back every window returns to its frame (patch 0044).
- **Game Mode**: every Windows program starts from a copy of Wine's loader inside the engine's own app bundle,
  `lib/wine/x86_64-unix/mavrik.app`, whose Info.plist declares a game that supports Game Mode
  (`LSApplicationCategoryType` `public.app-category.games`, `LSSupportsGameMode` and its older name
  `GCSupportsGameMode`), so macOS can give a full-screen game Game Mode (patch 0037, after neutron; in my tests a bundle like this got
  it in Wine's own full screen and in a full-screen Space). The same keys in the loader's built-in
  Info.plist did nothing: macOS read them only from a bundle. The
  bundle is laid and signed when the engine is assembled; nothing is made at run time. Its folder name is the name
  macOS shows when a Windows program first uses the local network, with the bundle's `NSLocalNetworkUsageDescription`.
  **Game Mode off**: with `MAVRIK_GAME_MODE=0` in the environment of the first process (exactly `0`; any other value
  or none keeps Game Mode on), Wine starts the program from `lib/wine/x86_64-unix/without-game-mode/mavrik.app`
  instead: the same bundle, with the same folder name and `CFBundleName`, without the three Game Mode keys and with
  its own identifier, `org.mavrik.engine.wine.without-game-mode` (patch 0037 version 3, revision 12). Every process
  the program starts inherits the variable with the rest of the Unix environment (Wine's `spawn_process` passes the
  parent's Unix environment, not the Windows one) and starts from the loader its parent chose, so a launcher's game
  follows it, and a Windows program can't change it for its children. The game's name in the menu bar, Cmd-Tab and
  the Dock is the same in both states. A launcher sets the variable per game, for a player's own choice. Processes a
  launcher started in the prefix before the game without the variable (Wine's `services.exe`, `explorer.exe` and
  `winedevice.exe` from its setup steps) keep running from the Game Mode bundle, and so does anything they start (a
  Windows service, an out-of-process COM server); Game Mode goes only to the frontmost full-screen app, the game.
  Wine's start no longer looks up the Mac's `.local` host name (patch 0041), so starting a Windows program doesn't
  touch the local network or wait on that prompt. A game that looks up its own machine gets the Mac's own addresses
  with no lookup (patch 0042), so a game that only looks itself up no longer waits on that prompt either.
- **The mouse cursor**: a cursor a Windows program hides is a transparent Mac cursor, set again after
  another app was in front and whenever the pointer comes back from another app's window, so the Mac
  arrow doesn't come back over a full-screen game after Cmd-Tab, at the Dock edge or on shake to locate
  (patches 0013, Wine merge request 11880, and 0014, this repository's follow-up to it). In Mission
  Control, App Exposé and Show Desktop, which leave the game the active app, a cursor clip lets the pointer
  go: while a game clips, the Mac driver reads the window list every 100 ms for WindowManager's full-display
  window at layer 19 (Mission Control and App Exposé on macOS 27) or 18 (Show Desktop), lifts the clip while
  it shows, and puts the clip and the hidden cursor back when it goes (patch 0015).
- **Raw mouse input**: while a game hides the cursor, holds the pointer with a cursor clip and is in front,
  the Mac pointer stops and a mouse's own counts (GameController's GCMouse, once per device report, up to
  1,000 moves a second, with none of macOS's acceleration) reach the game as relative moves, as Windows'
  raw input does; the game's own warps lose no motion. The trackpad keeps macOS's accelerated path, and
  Mission Control, App Exposé, Show Desktop and Cmd-Tab give the pointer back (patch 0039, after Recall's).
  The Mac driver option `RawMouseInput=n` turns it off.
- **Game controllers**: PlayStation pads reach games as XInput pads through SDL, like Xbox and Nintendo
  pads (`MAVRIK_PAD_HIDRAW=1` keeps them raw HID for one game); Nintendo pads are mapped by position, so the
  Pro Controller's right face button is XInput's B, where an Xbox pad has it; XInput rumble lasts until the
  game changes it; XInput's battery call answers as for a wired pad (patch 0035, from neutron). A pad's Home and Share
  buttons go to the game, not to macOS's Game Overlay and screenshots (patch 0036, from neutron).
  `MAVRIK_PAD_VIRTUAL=1` or `=<vid>:<pid>` attaches a scripted virtual pad, which `tools/gamepadprobe.c`
  (neutron's probe) checks in XInput, DirectInput, raw input and Windows.Gaming.Input.
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
  ([`bridge/`](../bridge/README.md)), and a program that starts the engine adds its `lib/wine` files to
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
