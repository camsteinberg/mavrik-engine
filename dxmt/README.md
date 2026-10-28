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
