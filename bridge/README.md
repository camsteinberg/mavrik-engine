# The Steam bridge

Valve's Steam bridge for mavrik's engine, built as its own archive beside it. A Windows game bought on
Steam talks to Steam through Valve's `steamclient.dll` or `steamclient64.dll`. The engine's loader
(patch 0004, Valve's) hands those calls to `lsteamclient.dll`, and lsteamclient passes them to the
Steam app on the Mac. This folder builds lsteamclient and Valve's `steam.exe` stub. Nothing in it is
part of the engine archive, and the engine refuses these files (`scripts/licences.py`).

It is separate because its code is Valve's, under Valve's terms, while the engine is LGPL. The bridge
can be changed or withdrawn alone.

## What it builds from

- **Proton** (ValveSoftware/Proton, `proton_11.0` at 5b89db9, 2026-09-04): `lsteamclient/`,
  `steam_helper/`, `LICENSE` and `LICENSE.proton` only. Pinned in [`inputs.json`](inputs.json) by
  the commit, the tarball's size and sha256, and a digest of the unpacked tree. GitHub makes a
  commit's tarball when asked, and its compression can change, so the tree digest is what pins the
  code (NotProton pins its Proton source the same way). A changed tarball fails the fetch on its
  sha256; it is re-pinned once `proton.py` confirms it unpacks to the same tree digest.
- **mavrik's patches** ([`patches/`](patches/)), applied in order, no fuzz:
  - `0001-register-components.patch`: adds `dlls/lsteamclient` and `programs/steam` to configure,
    so Wine's own make builds them.
  - `0002-lsteamclient-macos.patch`: what lsteamclient needs on a Mac. The Mac Steam app's
    `steamclient.dylib` lacks `Steam_IsKnownInterface` and `Steam_NotifyMissingInterface`, so both
    become optional. Also a macOS keysym branch, `NOMINMAX`, the SDK's `wchar.h` first, and `-lc++`.
  - `0003-steam-helper-macos.patch`: the stub keeps its in-place restart. Every other command it would
    forward to a native `steam` is logged and dropped, because forwarding would open Steam's window.
- **The engine's own tree**: the bridge is compiled in a clone of the engine's patched Wine sources,
  configured exactly as the engine (config.h must match), with the engine's toolchain and caches.
  An earlier test build proved this route with Spacewar.

## Building

After the engine's own four steps, in the same work folder:

```sh
bash bridge/build.sh WORK      # Proton's source, the tree, configure, make lsteamclient and steam.exe
bash bridge/assemble.sh WORK   # the bridge's folder, its build record, notice and licence folder
bash bridge/gates.sh WORK      # every gate, with the engine from WORK, then the self-test
bash bridge/pack.sh WORK       # the .tar.xz and its .sha256
```

`FETCH_ARGS`, `JOBS` and `FRESH` work as for the engine. The GitHub workflow does not run these steps
yet.

## The archive

`mavrik-steam-bridge-r<revision>-proton-<commit>-engine-r<engine revision>.tar.xz` holds one folder.
The bridge is built against one engine revision (config.h must match, and the Unix half links that
engine's `ntdll.so`), so the name carries it: a new engine revision makes a new archive name. The
engine revision is read from the engine's `inputs.json`.

| Path | What it holds |
|---|---|
| `lib/wine/i386-windows/` | `lsteamclient.dll` and `steam.exe`, 32-bit |
| `lib/wine/x86_64-windows/` | `lsteamclient.dll` and `steam.exe`, 64-bit |
| `lib/wine/x86_64-unix/` | `lsteamclient.so`, the Unix half, unsigned |
| `NOTICE.txt` | what this is and whose it is; not made by Valve |
| `licences/` | `README.txt`; Valve's Steamworks SDK licence (`lsteamclient/`); BSD-3-Clause for the stub (`steam-helper/`); the LGPL for Wine's start-up code and Proton's `cxx.h`, with a `README.txt` (`wine/`); this repository's `LICENSE` and `PATCHES.txt`, every patch's header (`mavrik-steam-bridge/`); `COMPONENTS.tsv` and `FILES.tsv` |
| `build-info.json` | the Proton commit, the patches, the engine it was built and gated with, every file's sha256 |

A program that starts the engine adds `lib/wine/*` to the engine's own `lib/wine`. That is the single
tree Proton and NotProton ship lsteamclient in, and the layout the gates test. The Unix half links
`@rpath/ntdll.so` with the run path `@loader_path/`, so it finds the engine's `ntdll.so` beside it.
32-bit games use the same Unix half through its wow64 call table, as the engine runs them in Wine's
wow64 mode.

## Checks

The gates in [`bridgegates.py`](bridgegates.py) fail the build. The self-test then feeds each gate one
bad input, and the gate must fail for that gate's reason:

| Gate | What must hold | Self-test's bad input |
|---|---|---|
| files | the five files; Wine builtins; i386 and AMD64 where they belong; the Unix half is x86_64 only | the 64-bit `lsteamclient.dll` in `i386-windows` |
| calltables | `nm` shows `__wine_unix_call_funcs` and `__wine_unix_call_wow64_funcs` | a library with only the 64-bit table |
| unsigned | `lsteamclient.so` has no code signature | the real Unix half, signed ad hoc |
| links | it loads only `@rpath/ntdll.so` and macOS's libraries; its only run path is `@loader_path/` | the real Unix half with `/opt/homebrew/lib` added |
| licences | every file covered; lsteamclient and steam.exe labelled by their part, never wine | `lsteamclient.so` labelled wine |
| buildpaths | no file names the build machine's folders | a notice naming the work folder |
| steamredirect | with the real lsteamclient added to a clone of the engine, in both halves: a stand-in `steamclient` DLL's export jumps into lsteamclient, lsteamclient's Unix half is loaded with its call table, and its answer comes back ([`tools/bridgeprobe.c`](tools/bridgeprobe.c)). `STEAM_COMPAT_CLIENT_INSTALL_PATH` points at a stand-in Steam library the gate builds (lsteamclient aborts without one); like the Mac Steam app's, it lacks `Steam_IsKnownInterface`, so patch 0002's fallback answers. No Steam app is touched. | the bridge turned off with `PROTON_DISABLE_LSTEAMCLIENT=1`; the files without `lsteamclient.so`; a stand-in Steam library that answers `Steam_IsKnownInterface` itself |

## Releases

A bridge release is a prerelease on this repository's releases page, tagged
`steam-bridge-r<revision>-engine-r<engine revision>`. It pairs with exactly one engine release, the
revision in its name: `steam-bridge-r1-engine-r5` goes with `11.0-cx26.3.0-r5` and no other engine, and
`steam-bridge-r1-engine-r6` with `11.0-cx26.3.0-r6`. A new engine revision gets its own bridge build and
prerelease.

A bridge prerelease carries:

- the archive (`.tar.xz`) and its `.sha256`;
- the gate and self-test results (`.gates.json`, `.gates-selftest.json`) and `.build-info.json`;
- the corresponding source: Proton's tarball at the pinned commit, and the bridge's patches
  (`0001` to `0003`). Wine's start-up code, the LGPL part both halves carry, is built from the
  engine's sources: the CrossOver source archive attached to the paired engine release (for r6,
  [`crossover-sources-26.3.0.tar.gz`](https://github.com/camsteinberg/mavrik-engine/releases/download/11.0-cx26.3.0-r6/crossover-sources-26.3.0.tar.gz)),
  with the engine's patches in that release's recipe archive.
  The recipe and scripts are this repository at the release's tag.

The GitHub workflow does not build the bridge yet. Until it does, a bridge prerelease is built on a
Mac by the four steps above, against the paired engine, and checked by the same gates and self-test.
`pack.sh` publishes nothing.

## Licence

- lsteamclient and the changes to it (`patches/0002-lsteamclient-macos.patch`) are under Valve's
  Steamworks SDK licence, `lsteamclient/LICENSE` in Proton.
- `steam.exe` and its change (`patches/0003-steam-helper-macos.patch`) are BSD-3-Clause, Valve's
  (`LICENSE.proton`).
- Both carry Wine's start-up code, LGPL-2.1-or-later. Its source is the engine's.
- lsteamclient also compiles in Proton's `lsteamclient/cxx.h` (Copyright 2012 Piotr Caban for
  CodeWeavers), LGPL-2.1-or-later. Its source is in Proton's tarball.
- The scripts here, `inputs.json`, `tools/` and `patches/0001-register-components.patch` are
  LGPL-2.1-or-later, like the rest of this repository.

Credits: Valve, for Proton's lsteamclient, steam_helper and the loader change; NotProton
(github.com/NotProtonNot/NotProton), which first showed lsteamclient working on a Mac with the Mac
Steam app, and the changes it needs there. Patch 0002 meets the same needs, written independently.
Nothing is copied from NotProton.
