# Parts and licences

Every part the engine carries, where it comes from, and its licence. Exact versions, addresses and
SHA-256 values are in [`inputs.json`](inputs.json). Inside each engine, `licences/` holds the full
licence texts and copyright notices, `licences/COMPONENTS.tsv` lists the parts, and
`licences/FILES.tsv` names the part every file belongs to.

| Part | Source | Licence | In the engine |
|---|---|---|---|
| Wine 11.0 | CodeWeavers' CrossOver 26.3.0 sources, media.codeweavers.com | LGPL-2.1-or-later | `bin/`, `lib/wine/`, `share/wine/` |
| Third-party code built into Wine's own files | Wine's `libs/` (zlib, libpng, libjpeg, libtiff, lcms2, libxml2, libxslt, mpg123, FAudio, FluidSynth, vkd3d, musl, LDAP, capstone, compiler-rt, GSM, JPEG XR, LibTomCrypt) | each its own (BSD, MIT, zlib, LGPL and others), texts in `licences/wine/libs/` | inside Wine's files |
| This repository's patches (0001, 0002, 0010 and 0018 to 0032 from highball-engine, which credits each one's authors: Gauthier Piarrette, athei, Tx, Paul Gofman, Proton and MacPorts; 0004 and 0005 from Valve's ValveSoftware/wine; 0007 adapted from CodeWeavers' CW HACK 22144; 0009, 0011 and 0012 from upstream Wine; 0013 from Wine merge request 11880, Elvin Hayatov; 0035 and 0036 adapted from neutron's 0017, and 0037 after neutron's 0003 and 0006 loader hunks, the neutron contributors; 0039 after Recall's wine-mouselook.patch, Josh Nelson) | `patches/` | LGPL-2.1-or-later | inside Wine's files |
| Wine Mono 11.3.0 | github.com/wine-mono/wine-mono | MIT, LGPL-2.1-or-later and others (its COPYING); its notices come from its source archive: Mono and the projects in `mono/external` (BoringSSL, corefx, CoreRT, ASP.NET Web Stack, Cecil, the linker, Rx), FNA (MS-PL and MIT), FAudio, FNA3D, MojoShader, dav1dfile, SDL3 (with HIDAPI), SDL2-CS and SDL3-CS (zlib), winforms and WPF (MIT), monoDX | `share/wine/mono/` |
| Wine Gecko 2.47.4 | dl.winehq.org | MPL-2.0; its own notices are its about:license page, copied to `licences/wine-gecko/license.html` | `share/wine/gecko/` |
| MoltenVK 1.4.2 | github.com/KhronosGroup/MoltenVK | Apache-2.0; includes SPIRV-Cross and SPIRV-Tools (Apache-2.0) and cereal (BSD-3-Clause) | `lib/libMoltenVK.dylib` |
| DXMT main at 3b252590cb, 64-bit files | github.com/3Shain/dxmt, built here from its source with this repository's `dxmt/patches` | LGPL-2.1-or-later (releases up to v0.80 were MIT, kept as LICENSE.OLD); includes LLVM 15.0.7 (Apache-2.0 WITH LLVM-exception, with its regex and ConvertUTF notices), Microsoft's DXBCParser (MIT), NVIDIA's nvapi headers (MIT), DXVK code (zlib), dxbc-spirv's MD5 code (MIT) and Wine's start-up code (LGPL-2.1-or-later) | `lib/wine/x86_64-windows/` (d3d11, dxgi, d3d10core, winemetal, nvapi64, nvngx), `lib/wine/x86_64-unix/winemetal.so` |
| GnuTLS 3.8.13 | gnutls.org, built here | LGPL-2.1-or-later; its own copies of libtasn1 (LGPL-2.1-or-later) and libunistring (LGPL-3.0-or-later or GPL-2.0-or-later); includes CRYPTOGAMS assembly (BSD-style), inih (BSD-3-Clause) and crypto-auditing's header (MIT) | `lib/libgnutls.30.dylib` |
| Nettle 4.0 | ftp.gnu.org, built here | LGPL-3.0-or-later or GPL-2.0-or-later (its DES code's notice: `descore.README`) | `lib/libnettle.*`, `lib/libhogweed.*` |
| GMP 6.3.0 | ftp.gnu.org, built here | LGPL-3.0-or-later or GPL-2.0-or-later | `lib/libgmp.*` |
| FreeType 2.15.0 | freetype.org, built here | FreeType License (FTL); its BDF and PCF drivers carry their own X11-style notices | `lib/libfreetype.6.dylib` |
| SDL3 3.4.18 | github.com/libsdl-org/SDL, built here | Zlib; includes HIDAPI (BSD terms) and yuv2rgb (BSD-3-Clause) | `lib/libSDL3.dylib` |
| sdl2-compat 2.32.74 (the SDL2 interface, on SDL3) | github.com/libsdl-org/sdl2-compat, built here | Zlib | `lib/libSDL2-2.0.0.dylib` |
| Liberation fonts 2.1.5 (Liberation Sans, Serif and Mono; metric-compatible with Arial, Times New Roman and Courier New) | github.com/liberationfonts/liberation-fonts (its TTF archive, mirrored on this repository's releases), unchanged | SIL Open Font License 1.1 (its LICENSE, in `licences/liberation-fonts/`) | `share/wine/fonts/Liberation*.ttf`; wine.inf copies them into each prefix's `C:\windows\Fonts` as arial.ttf, arialbd.ttf, cour.ttf, courbd.ttf, georgia.ttf and times.ttf |
| GStreamer 1.28.8 (core, base, good, bad, ugly, libav: the plugins Wine uses) | GStreamer's official macOS packages | LGPL-2.1-or-later (the MPEG-PS demuxer: MPL-1.1 or LGPL-2.1-or-later) | `lib/libgst*`, `lib/gstreamer-1.0/` |
| GLib 2.82.4 | inside GStreamer's packages | LGPL-2.1-or-later | `lib/libglib*`, `lib/libgobject*`, `lib/libgio*`, `lib/libgmodule*` |
| FFmpeg 7.1 (LGPL build) | inside GStreamer's packages | LGPL-2.1-or-later | `lib/libav*`, `lib/libsw*` |
| proxy-libintl 0.5 | inside GStreamer's packages | LGPL-2.0-or-later | `lib/libintl.8.dylib` |
| mpg123 1.32.7 | inside GStreamer's packages | LGPL-2.1 | `lib/libmpg123.*` |
| libffi, PCRE2, ORC, zlib, bzip2, FLAC, Ogg, Vorbis, Theora, Opus | inside GStreamer's packages | MIT, BSD-3-Clause, BSD-2-Clause, Zlib, bzip2 | `lib/` |

Not in the media component on purpose: x264, x265, a52dec, libdvdread, libdvdnav, OpenH264,
mpeg2dec and dtsdec (GPL or patent-encumbered).

Never bundled or downloaded: D3DMetal (Apple's Game Porting Toolkit, under Apple's licence).

Not in the engine: Valve's Steam bridge (lsteamclient and the steam.exe stub). It is built from
[`bridge/`](bridge/) as its own archive, with its own licence folder: lsteamclient under Valve's
Steamworks SDK licence, steam.exe under BSD-3-Clause, both carrying Wine's start-up code (LGPL).
lsteamclient also compiles in Proton's `lsteamclient/cxx.h` (CodeWeavers, LGPL-2.1-or-later), whose
source is in Proton's tarball. The engine's licence step refuses those files, so they are never listed
as Wine's.

A release also carries the corresponding source of every LGPL and MPL part (see "Releases" in the
README); for the media component that is the tarballs GStreamer's build recipes (cerbero 1.28.8)
built it from, and cerbero with its patches.

Build tools that are not shipped: mingw-w64 gcc, bison and ccache (GPL), Xcode's clang.
