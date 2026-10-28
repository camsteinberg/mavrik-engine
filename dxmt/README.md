# DXMT's source

The engine carries DXMT's own CI package (`inputs.json`, `dxmt`). A release carries its complete source,
pinned in `inputs.json`'s `release_sources`, made here so the same commits give the same bytes:

- `dxmt-source`: `make-source.sh SRC OUT` makes DXMT at a148782d43 with its two submodules filled
  (`external/nvapi` d08488fcc8, `include/native/directx` 9df86f2341) from a clone with its submodules:
  `git archive` of each, one folder named after the commit, `gzip -n`. GitHub's tarball of a commit leaves
  the submodules empty.
- `dxmt-winecrt0-source`: DXMT's `winemetal.dll` statically links Wine's start-up code (winecrt0, LGPL) from
  the Wine build DXMT's CI uses, 3Shain's Wine 8.16 (release `v8.16-3shain`, commit 4dd8a2d6dc). Its source
  travels with the release: `winecrt0-closure.py REPO COMMIT` lists `dlls/winecrt0` and every header it
  includes, transitively (the `.idl` source of a generated header, `config.h.in` for `config.h`), into
  `winecrt0-files.txt`; `make-winecrt0-source.sh REPO winecrt0-files.txt OUT` archives those with Wine's
  `COPYING.LIB`, `LICENSE`, `AUTHORS` and `VERSION`. The four names it cannot resolve (`dlfcn.h`, `elf.h`,
  `link.h`, `x86intrin.h`) are system and compiler headers, used only outside Windows builds.

Both are attached to the 11.0-cx26.3.0-r7 release.

## Patches

mavrik's changes to DXMT, applied in order to DXMT's source at the pinned commit, no fuzz.

| Patch | Why mavrik needs it |
|---|---|
| `0001-frame-latency-to-presentation.patch` | Under vsync or a frame cap, DXMT counted a frame as done at GPU completion, so finished frames waiting in Core Animation's drawables added about 2.4 frames of input latency (mavrik's S214 meter). The frame latency limit now counts to presentation, as in DXVK and on Windows; vsync off is unchanged. Also DXGI's rules for `SetMaximumFrameLatency` and DXVK's `dxgi.maxFrameLatency`. Written by an AI agent, so not offered to DXMT as a pull request (DXMT refuses AI-written code); the finding goes to DXMT as an issue. Status: built into the lab engine r7p (S215), not measured yet. |

## How the lab built it (S215)

DXMT's CI job `build-gcc-release-x86_64-windows-cross` at a148782d43, which made revision 7's package:

- DXMT at a148782d43 with its submodules (`external/nvapi` d08488fc, `include/native/directx` 9df86f23).
- LLVM 15.0.7 (`llvm-15.0.7.src.tar.xz` and `cmake-15.0.7.src.tar.xz` from LLVM's release), built for
  x86_64 macOS with the CI's flags (Release, assertions on, no targets, no tools, no zstd).
- 3Shain's Wine `v8.16-3shain` (`wine.tar.gz`, sha256 289c7f19...4f10) for winebuild and the libraries
  winemetal links.
- Homebrew's mingw-w64 (GCC 16.2.0), meson 1.10.0, `--cross-file build-win64.txt -Denable_nvapi=true
  -Denable_nvngx=true --buildtype release --strip`, and `MACOSX_DEPLOYMENT_TARGET=15.0` (the CI's
  macOS 15 default; without it winemetal.so asks for the build Mac's macOS).
- Xcode 26.2, where the CI used Xcode 16.1. Built unpatched, the six DLLs match revision 7's in size
  and exports, and dxgi, d3d10core, winemetal, nvapi64 and nvngx differ only in their timestamps.
  d3d11.dll differs in its embedded Metal shader library (Xcode's Metal compiler), and winemetal.so in
  libc++'s version tag; its C exports and linked libraries match.
- DXMT's version string comes from `git describe --always`; the CI's shallow checkout gives
  `a148782`, a clone with tags gives a longer one, so the lab dropped the tags to match.

Revision 8 should pin these inputs like the others and record the toolchain in build-info.json.
