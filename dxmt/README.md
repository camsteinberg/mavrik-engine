# DXMT

From revision 8 the engine builds DXMT's 64-bit files from source with the patches in `patches/`
(`scripts/build-dxmt.sh`). Revision 7 and earlier carried DXMT's own CI package.

## How the engine builds it

`build-dxmt.sh` follows DXMT's own CI job `build-gcc-release-x86_64-windows-cross`, with every input
pinned in `inputs.json` by URL, size and SHA-256 and mirrored on this repository's releases:

- `dxmt-source`: DXMT at the pinned commit with its two submodules (`external/nvapi`,
  `include/native/directx`), made by `make-source.sh`.
- `dxmt-llvm-source` and `dxmt-llvm-cmake`: LLVM 15.0.7, DXMT's `LLVM_VERSION`, built for x86_64 macOS with
  the CI's options (Release, assertions on, no targets, no tools, no zstd). It is kept in the work folder
  and rebuilt only when its pins, options or the toolchain change.
- `dxmt-wine`: 3Shain's prebuilt Wine 8.16 (`v8.16-3shain`), the Wine DXMT's CI links against.
- `meson` 1.10.0 and `ninja`, PyPI's wheels, in the build's own venv. Homebrew's mingw-w64 gcc compiles the
  Windows side; the Xcode in `toolchain` (26.2) compiles the Unix side and DXMT's Metal shaders, where the CI
  uses Xcode 16.1. The macOS target is the CI's 15.0.

Each patch applies in order with no fuzz and no offset, or the build stops. DXMT's version string comes
from `git describe`, which the source archive cannot answer, so a stand-in answers
`<commit, 10 characters>-mavrik.<number of patches>`: DXMT's log and HUD then name the commit and say the
build is mavrik's. Every compiler gets `-ffile-prefix-map`, so no build path lands in the files. The
engine's `build-info.json` records the commit, the version string, each patch and each file's SHA-256, and
the `dxmt` gate checks the engine against that record.

Not built: 32-bit DXMT (the CI's `gcc-release-x86-windows-cross` job). It would move 32-bit Direct3D 11
games off Wine's own d3d11, a change to be measured on its own.

## Patches

mavrik's changes to DXMT, applied in order to DXMT's source at the pinned commit.

| Patch | Why mavrik needs it |
|---|---|
| `0001-set-maximum-frame-latency-follows-dxgi.patch` | DXMT stored SetMaximumFrameLatency's value as it came, so a game that passes 0 (DXGI's "back to the default of 3") had every Present wait for the frame just submitted to finish on the GPU: no CPU and GPU overlap. Civilization VI's DX11 program passes 0: 38 to 39 fps without this, 95.5 to 97.7 with it (mavrik S215, interleaved). Now 0 means 3 and values above 16 are refused, as Microsoft documents; GetMaximumFrameLatency returns the application's value; DXVK's `dxgi.maxFrameLatency` can cap it. Written by an AI agent, so offered to DXMT as an issue, not a pull request. |
| `0002-frame-latency-to-presentation.patch` | Under vsync or a frame cap, DXMT counted a frame as done at GPU completion, so finished frames waiting in Core Animation's drawables added about 2.4 frames of input latency (mavrik's S214 meter). The frame latency limit now counts to presentation, as in DXVK and on Windows; vsync off is unchanged. A presentation wait over 100 ms is given up and logged each time (at most once a second), then waits stop until a frame is presented again. Measured in mavrik's S215 lab against the same build without it: 2.44 frames less latency under vsync, frame rate held. Written by an AI agent, so the finding goes to DXMT as an issue. |

## DXMT's source in a release

A release carries DXMT's complete source and the source of what it links in, made here so the same
commits give the same bytes:

- `dxmt-source` (an input since revision 8): `make-source.sh SRC COMMIT OUT` makes DXMT at COMMIT with its two
  submodules filled at the commits COMMIT records, from a clone with its submodules: `git archive` of each,
  one folder named after the commit, `gzip -n`. GitHub's tarball of a commit leaves the submodules empty.
  The patches travel in the release's recipe archive (`dxmt/patches`).
- `dxmt-winecrt0-source` (`release_sources`): DXMT's `winemetal.dll` statically links Wine's start-up code
  (winecrt0, LGPL) from 3Shain's Wine 8.16 (release `v8.16-3shain`, commit 4dd8a2d6dc). `winecrt0-closure.py
  REPO COMMIT` lists `dlls/winecrt0` and every header it includes, transitively (the `.idl` source of a
  generated header, `config.h.in` for `config.h`), into `winecrt0-files.txt`; `make-winecrt0-source.sh REPO
  winecrt0-files.txt OUT` archives those with Wine's `COPYING.LIB`, `LICENSE`, `AUTHORS` and `VERSION`. The
  four names it cannot resolve (`dlfcn.h`, `elf.h`, `link.h`, `x86intrin.h`) are system and compiler
  headers, used only outside Windows builds. First attached to the 11.0-cx26.3.0-r7 release.
