# Patch series

Applied in order to the pinned Wine source (`inputs.json`, `crossover-sources`). The build stops if a
patch does not apply exactly (no fuzz, no rejects). Each patch keeps its own header. A patch that
upstream ships is removed here in the change that moves the pinned source.

| Patch | From | Why mavrik needs it |
|---|---|---|
| `0001-use-the-real-user-name.patch` | [highball-engine](https://github.com/gauthierpiarrette/highball-engine) | CrossOver names every Windows user "crossover"; mavrik's existing game folders use the Mac user's name, and saves live under it, so without this a game would lose sight of its saves. |
| `0002-wined3d-auto-renderer-opengl-first.patch` | [highball-engine](https://github.com/gauthierpiarrette/highball-engine) | CrossOver picks Vulkan (MoltenVK) first for Wine's own Direct3D; mavrik's Direct3D 9 and 32-bit games were tested on OpenGL, the upstream Wine default, and stay on it. |
| `0003-mavrik-engine-identity.patch` | this repository | The CrossOver tree presents the loader as CrossOver (bundle identifier `com.codeweavers.CrossOver.wineloader`, shared with CrossOver and Apple's Game Porting Toolkit) and sends crash reports to CodeWeavers. This engine is not CrossOver: the loader becomes `org.mavrik.engine` (each game's own name stays in its app menu), the crash dialog links to this repository's issues, and the browser window and an uninstall entry lose CrossOver's names. Not for upstream, which uses its own names already. |

## Checked and not needed

- **DXMT's hooks in the Mac driver.** DXMT looks up `macdrv_functions` in `winemac.so` first, and
  only falls back to five separate function names when that is missing. The CrossOver tree already
  exports `macdrv_functions` (`dlls/winemac.drv/d3dmetal.c`, made for D3DMetal and DXMT), and its
  layout matches what DXMT v0.80 reads. The five fallback names stay hidden, so they need no patch.
  The `winemac` gate checks both the export and the layout on every build.
- **highball-engine's 0003 (`WINEDLLPATH_PREPEND`).** mavrik puts DXMT's files straight into the
  engine instead of an overlay folder.
- **highball-engine's other patches** fix specific games or measured faults mavrik has not met yet.
  Each can be adopted with its own reason when a mavrik game needs it.
