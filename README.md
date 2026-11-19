# mavrik-engine

The Wine build that [Mavrik](https://getmavrik.app) downloads to run Windows games on Apple silicon
Macs.

Mavrik is a free Mac launcher for Steam, Epic and GOG games. The app is closed source. Everything it
changes in Wine, DXMT and Valve's Steam bridge is here, under the LGPL apart from two bridge patches
that keep Valve's licences. If you only want to play, get Mavrik; this repository is for people who
want to see or change what runs underneath.

This is not CrossOver. It is built from the Wine sources CodeWeavers publishes
([more below](#relation-to-crossover)).

## Status

- Current revision: [r13](https://github.com/camsteinberg/mavrik-engine/releases/tag/11.0-cx26.3.0-r13),
  used by Mavrik 0.1.10. Both are in beta.
- Wine 11.0 (CrossOver 26.3.0 sources) with the 44 patches in [`patches/`](patches/README.md). DXMT
  built from source with two patches, for Direct3D 10 and 11. Direct3D 12 games use Apple's D3DMetal
  ([below](#d3dmetal)).
- Built for Intel (x86_64); on Apple silicon it runs under Rosetta 2. 32-bit Windows games run too.
  DXMT needs macOS 15 or later.
- I build releases on my Mac with the scripts in [`scripts/`](scripts/). The GitHub workflow here is
  untested: it has never built the engine ([#6](https://github.com/camsteinberg/mavrik-engine/issues/6)).

## Known problems

- Figment hangs on a black window, and I have not found the cause ([#1](https://github.com/camsteinberg/mavrik-engine/issues/1)).
- After the Mac's display mode changes to a smaller mode and back, Civilization VI's window sits 37
  points low ([#2](https://github.com/camsteinberg/mavrik-engine/issues/2)).
- Star Wars Battlefront II (2005) did not fill the screen until Mavrik's Picture setting for it was
  changed to Quality. Cause not known ([#5](https://github.com/camsteinberg/mavrik-engine/issues/5)).
- One long frame about 30 s after a game starts, when Wine saves its registry ([#3](https://github.com/camsteinberg/mavrik-engine/issues/3)).
- Hitches at scene loads come back on every launch, because DXMT creates its pipelines again. Last
  measured on r5 ([#4](https://github.com/camsteinberg/mavrik-engine/issues/4)).
- No native arm64 build yet, so everything depends on Rosetta 2 ([#7](https://github.com/camsteinberg/mavrik-engine/issues/7)).

The [issues](https://github.com/camsteinberg/mavrik-engine/issues) have the rest.

## Bugs

A game that misbehaves on this engine is a bug for this repository: open an
[issue](https://github.com/camsteinberg/mavrik-engine/issues/new/choose). Wine's crash dialog links
here too. Please don't report it to CodeWeavers, WineHQ, DXMT or Valve. This is a patched build, and
their trackers are for their own releases.

Problems with the Mavrik app itself (the library, downloads, sign-in) go to
[getmavrik.app/support](https://getmavrik.app/support).

## D3DMetal

D3DMetal is Apple's, not part of this engine. The build never uses it and no engine archive contains
it.

For Direct3D 12 games, Mavrik shows Apple's licence and, only after the player accepts it, downloads
Apple's unmodified image from this repository's
[`d3dmetal-4.0b3`](https://github.com/camsteinberg/mavrik-engine/releases/tag/d3dmetal-4.0b3) release.
That file is under Apple's Game Porting Toolkit licence, not the LGPL. It is hosted here only so
Mavrik can fetch it; Mavrik is free, and Apple's licence allows non-commercial distribution (section
2A(iii) of `License.rtf` inside the image).

## What it is built from

- Wine 11.0, from CodeWeavers' CrossOver 26.3.0 sources, with the patches in [`patches/`](patches/).
  [`patches/README.md`](patches/README.md) says where each one comes from and why it is there.
- [DXMT](https://github.com/3Shain/dxmt) at main 647b0020ba, built from source with the two patches
  in [`dxmt/patches/`](dxmt/README.md): Direct3D 10 and 11 on Metal.
- MoltenVK 1.4.2, for games that use Vulkan.
- GStreamer 1.28.8 and FFmpeg 7.1 from GStreamer's macOS packages, LGPL parts only.
- Wine Mono 11.3.0 and Wine Gecko 2.47.4, unpacked, so a new Wine prefix never downloads them.
- GnuTLS, FreeType, and SDL3 with sdl2-compat, built here from their source releases.
- The Liberation fonts 2.1.5.

Every input is pinned by URL, size and SHA-256 in [`inputs.json`](inputs.json), and a release build
refuses an input without a pinned hash. [NOTICE.md](NOTICE.md) lists every part with its licence.

Valve's Steam bridge (lsteamclient, which lets a Windows game bought on Steam talk to the Mac Steam
app) is not in the engine. It is built from Proton's source as its own archive
([`bridge/`](bridge/README.md)).

## Releases

- `11.0-cx26.3.0-rN` is engine revision N: the archive, its SHA-256, the gate results, the build
  record, and the source of every LGPL and MPL part in it.
- `steam-bridge-r1-engine-rN` is the Steam bridge built against that revision.
- `inputs-…` releases mirror build inputs whose own addresses are not stable.
- `d3dmetal-4.0b3` is Apple's file ([above](#d3dmetal)).

An engine archive is a self-contained Wine folder and runs without Mavrik;
[docs/launchers.md](docs/launchers.md) says what is in it. Old revisions stay up because installed
copies of Mavrik download them by URL and check each against a hash they carry.

## Building

```sh
bash scripts/build.sh WORK      # inputs, toolchain check, sources and patches, Unix libraries, Wine
bash scripts/assemble.sh WORK   # the engine folder, its build record and its licence folder
bash scripts/gates.sh WORK      # every gate, then the self-test
bash scripts/pack.sh WORK       # the .tar.xz and its .sha256
```

It needs Xcode 26.2 and, from Homebrew, bison, mingw-w64, cmake and pkg-config; on Apple silicon,
Rosetta too. [docs/building.md](docs/building.md) has the rest.

## More

- [docs/launchers.md](docs/launchers.md): what is in an engine archive, and the variables and options
  a launcher can set (the game's name in the Dock, Game Mode, raw mouse input, controllers, the notch).
- [docs/gates.md](docs/gates.md): the gates, the checks every build has to pass, and how each is
  shown to fail on a bad input.
- [docs/building.md](docs/building.md): the toolchain, build notes, and what a release carries.
- [patches/README.md](patches/README.md), [dxmt/README.md](dxmt/README.md) and
  [bridge/README.md](bridge/README.md): each patch, where it comes from and why.

## Relation to CrossOver

This is a build of Wine from CodeWeavers' published CrossOver sources. It is not CrossOver.
"CrossOver" is a trademark of CodeWeavers. CodeWeavers publishes the Wine sources inside each
CrossOver release under the LGPL, and this build uses them unchanged apart from the patches in
[`patches/`](patches/).

The engine never presents itself as CrossOver. Patch 0003 gives the Wine loader its own identity
(`org.mavrik.engine`, with each game's own name in its app menu), points Wine's crash dialog at this
repository's issues, and removes CrossOver's names from the places a player could see them. The
`identity` gate checks this on every build.

## Credits

- CodeWeavers, for CrossOver and for publishing its Wine sources, and the Wine project.
- [highball-engine](https://github.com/gauthierpiarrette/highball-engine) (LGPL-2.1-or-later): the
  closest recipe to this one. Patches 0001, 0002, 0010 (its MSync fix) and 0018 to 0032 come from it unchanged, with
  the authors named in each one's header (Gauthier Piarrette, athei, Tx, Paul Gofman and Proton's developers, and
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
- VLC, whose handling of the camera housing (a black window, the picture below the safe area) patch 0040
  follows.
- Wine's developers, whose commits patches 0009, 0011 and 0012 carry unchanged (Zhiyi Zhang's Core Audio
  period fix and Giovanni Mascellani's guard; Esme Povirk's Wine Mono updates; Alexandre Julliard's FAudio
  imports and Alex Henrie's FAudio fix).
- Elvin Hayatov, whose Wine merge request 11880 patch 0013 carries (the transparent hidden cursor).
- Ivo Ivanov, whose route in Wine bug 60322 (no lookup of a `.local` host name) patch 0041 follows.
- OpenAL Soft, whose use of Apple's default output unit patch 0043 follows, and winepulse and winealsa, whose first,
  default endpoint it follows. Nothing is copied.
- [neutron](https://github.com/fourlexboehm/neutron) (LGPL-2.1-or-later), a Proton-style Steam tool for
  macOS: patches 0035 and 0036 adapt its game controller patch (`0017-winebus-sdl-gamepads.patch`), and
  `tools/gamepadprobe.c` is its `tests/gamepad_list.c` with Mavrik's variable names.
- [Recall](https://github.com/AsherJN/recall) (Josh Nelson): patch 0039 follows its `wine-mouselook.patch`
  (a mouse's raw counts from GameController while a game holds the pointer), written for this tree.
- CodeWeavers' CW HACK 22144, which patch 0007 adapts: CrossOver already starts each Windows program
  through a link named after it.
- The DXMT, MoltenVK, GStreamer, FFmpeg, GnuTLS, FreeType and SDL authors, and the Liberation fonts'
  designers (Ascender, Steve Matteson, Red Hat). Proton, whose Windows font names 0017 follows and
  whose 32-bit compiler flags (`i386_CFLAGS`) `build-wine.sh` uses.
- The media component's script started as Mavrik's own `make-media-component.sh`.

## Licence

The recipe, the scripts and the patches are LGPL-2.1-or-later ([LICENSE](LICENSE)), like Wine,
except `bridge/patches/0002` (Steamworks SDK licence) and `0003` (BSD-3-Clause); see
[bridge/README.md](bridge/README.md#licence).
[NOTICE.md](NOTICE.md) lists every part the engine carries, where it comes from and its licence.
Inside each engine, `licences/` holds the full licence texts and copyright notices.
