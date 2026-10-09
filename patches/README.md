# Patch series

Applied in order to the pinned Wine source (`inputs.json`, `crossover-sources`). The build stops if a
patch does not apply exactly (no fuzz, no rejects). Each patch keeps its own header. A patch that
upstream ships is removed here in the change that moves the pinned source.

| Patch | From | Why mavrik needs it |
|---|---|---|
| `0001-use-the-real-user-name.patch` | [highball-engine](https://github.com/gauthierpiarrette/highball-engine) | CrossOver names every Windows user "crossover"; mavrik's existing game folders use the Mac user's name, and saves live under it, so without this a game would lose sight of its saves. |
| `0002-wined3d-auto-renderer-opengl-first.patch` | [highball-engine](https://github.com/gauthierpiarrette/highball-engine) | CrossOver picks Vulkan (MoltenVK) first for Wine's own Direct3D; mavrik's Direct3D 9 and 32-bit games were tested on OpenGL, the upstream Wine default, and stay on it. |
| `0003-mavrik-engine-identity.patch` | this repository | The CrossOver tree presents the loader as CrossOver (bundle identifier `com.codeweavers.CrossOver.wineloader`, shared with CrossOver and Apple's Game Porting Toolkit) and sends crash reports to CodeWeavers. This engine is not CrossOver: the loader becomes `org.mavrik.engine` (each game's own name stays in its app menu), the crash dialog links to this repository's issues, and the browser window and an uninstall entry lose CrossOver's names. Not for upstream, which uses its own names already. |
| `0004-steam-bridge-loader.patch` | Valve, [ValveSoftware/wine](https://github.com/ValveSoftware/wine) `proton_11.0` at dc26e61, ported to this tree | Valve's Steam bridge: a game's `steamclient` DLL hands its calls to lsteamclient, which talks to the Mac Steam app, so a Windows game bought on Steam runs with one sign-in and no Windows Steam. lsteamclient itself is its own archive. Valve's Windows Steam client run in this engine without lsteamclient needs `PROTON_DISABLE_LSTEAMCLIENT=1`, as in Proton. Not in WineHQ; carried as the one exception in mavrik's upstream-first rule. |
| `0005-makedep-cpp-sources.patch` | Valve, ValveSoftware/wine `proton_11.0` (one table line) | makedep reads `.cpp` sources, so lsteamclient's C++ Unix half builds against this tree with Wine's own make. Changes nothing in the engine's own build: the Wine tree has no C++ file. |
| `0006-game-name-in-the-dock.patch` | this repository, following Chromium, Firefox and WebKit | The Dock and the app switcher showed every game as "wine". The Mac driver now sets the process's LaunchServices display name to the name its app menu already uses (the program's, or `WINEPRELOADERAPPNAME`), with a private call looked up at run time, and processes a game starts keep that name. On a macOS without the call, the name stays "wine". To be offered upstream. |

## Checked and not needed

- **DXMT's hooks in the Mac driver.** DXMT looks up `macdrv_functions` in `winemac.so` first, and
  only falls back to five separate function names when that is missing. The CrossOver tree already
  exports `macdrv_functions` (`dlls/winemac.drv/d3dmetal.c`, made for D3DMetal and DXMT), and its
  layout matches what DXMT v0.80 reads. The five fallback names stay hidden, so they need no patch.
  The `winemac` gate checks both the export and the layout on every build.
- **athei/wine's loader check (revision 2's patch 0004, removed in revision 3).** Without it, every
  32-bit program was relaunched through `start.exe`. Wine's own setting `WINEARCH=wow64` does the
  same with no patch: Wine names no alternate loader in that mode, so the program runs in the
  process it starts. mavrik sets it for every Wine program it starts in a game's folder.
- **highball-engine's 0003 (`WINEDLLPATH_PREPEND`).** mavrik puts DXMT's files straight into the
  engine instead of an overlay folder.
- **highball-engine's other patches** fix specific games or measured faults mavrik has not met yet.
  Each can be adopted with its own reason when a mavrik game needs it.
