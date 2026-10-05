#!/usr/bin/env python3
"""The engine's licence folder.

  licences.py media-notices WORK
      Writes WORK/media-notices/<project>.txt (licence texts and notices for every project the
      media component takes files from), from the pinned licence texts and mpg123's source.

  licences.py write WORK ENGINE REPO
      Writes ENGINE/licences/: one folder per component with its full licence texts and
      copyright notices, COMPONENTS.tsv (component, version, licence, source, notice files)
      and FILES.tsv (every file in the engine and the component it belongs to; a line with a
      '*' is a pattern). Reads WORK/contributions.json from assemble.py.
"""
import fnmatch
import json
import os
import shutil
import sys
import tarfile


def load(work):
    paths = json.load(open(os.path.join(work, "downloads", "paths.json")))
    inputs = json.load(open(open(os.path.join(work, "inputs.path")).read().strip()))
    return paths, inputs


def text_of(paths, ref, cache={}):
    """A pinned licence text by its id, or KEY:MEMBER for a file inside a pinned source archive."""
    if ":" not in ref:
        return open(paths[ref], encoding="utf-8", errors="replace").read()
    key, member = ref.split(":", 1)
    if key not in cache:
        with tarfile.open(paths[key]) as t:
            cache[key] = {os.path.basename(m.name): t.extractfile(m).read().decode("utf-8", "replace")
                          for m in t.getmembers() if m.isfile() and m.name.count("/") == 1}
    return cache[key][member]


def media_notices(work):
    paths, inputs = load(work)
    dest = os.path.join(work, "media-notices")
    os.makedirs(dest, exist_ok=True)
    for project, info in inputs["media_projects"].items():
        parts = [f"{project} {info['version']}, as built into GStreamer "
                 f"{inputs['inputs']['gstreamer-runtime']['version']}'s official macOS package.\n"
                 f"Licence: {info['licence']}\nSource: {info['source']}\n"]
        for ref in info["texts"]:
            parts.append(f"\n----- {ref} -----\n\n" + text_of(paths, ref))
        open(os.path.join(dest, project + ".txt"), "w").write("".join(parts))
    print(f"media notices for {len(inputs['media_projects'])} projects in {dest}")


COMPONENT_INFO = {
    # component: (licence, what it is)
    "wine": ("LGPL-2.1-or-later", "Wine, built from CodeWeavers' published CrossOver sources, with this repository's patches"),
    "wine-mono": ("MIT AND LGPL-2.1-or-later AND others, see COPYING", "Wine Mono, the .NET runtime Wine uses"),
    "wine-gecko": ("MPL-2.0", "Wine Gecko, the HTML engine Wine uses"),
    "moltenvk": ("Apache-2.0 (with cereal: BSD-3-Clause)", "MoltenVK, Vulkan on Metal"),
    "dxmt": ("MIT (with LLVM: Apache-2.0 WITH LLVM-exception, and others listed)", "DXMT, Direct3D 10 and 11 on Metal (64-bit files)"),
    "gmp": ("LGPL-3.0-or-later OR GPL-2.0-or-later", "GNU MP, used by GnuTLS"),
    "nettle": ("LGPL-3.0-or-later OR GPL-2.0-or-later", "Nettle, used by GnuTLS"),
    "gnutls": ("LGPL-2.1-or-later (includes libtasn1: LGPL-2.1-or-later, libunistring: LGPL-3.0-or-later OR GPL-2.0-or-later)", "GnuTLS, Wine's TLS"),
    "freetype": ("FTL", "FreeType, Wine's font rendering"),
    "sdl2": ("Zlib", "SDL2, Wine's game controller support"),
    "mavrik-engine": ("LGPL-2.1-or-later", "this repository's build files and build record"),
    "licences": ("(the licence texts themselves)", "this folder"),
}
SOURCE_KEY = {"wine": "crossover-sources", "wine-mono": "wine-mono", "wine-gecko": "wine-gecko-x86",
              "moltenvk": "moltenvk", "dxmt": "dxmt", "gmp": "gmp", "nettle": "nettle", "gnutls": "gnutls",
              "freetype": "freetype", "sdl2": "sdl2"}


def write(work, engine, repo):
    paths, inputs = load(work)
    contrib = json.load(open(os.path.join(work, "contributions.json")))
    lic = os.path.join(engine, "licences")
    if os.path.exists(lic):
        shutil.rmtree(lic)
    os.makedirs(lic)
    notices = {}

    def put(component, name, data):
        p = os.path.join(lic, component, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(p, mode) as f:
            f.write(data)
        notices.setdefault(component, []).append(os.path.relpath(p, lic))

    def put_file(component, name, src):
        put(component, name, open(src, "rb").read())

    # Wine, and the third-party code built into Wine's own files (libs/).
    src = os.path.join(work, "wine-src")
    for name in ("COPYING.LIB", "LICENSE", "LICENSE.OLD", "AUTHORS"):
        if os.path.isfile(os.path.join(src, name)):
            put_file("wine", name, os.path.join(src, name))
    libs = os.path.join(src, "libs")
    for lib in sorted(os.listdir(libs)):
        d = os.path.join(libs, lib)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            up = name.upper()
            if up.startswith(("COPYING", "LICENSE", "LICENCE", "COPYRIGHT", "AUTHORS")):
                put_file("wine", f"libs/{lib}/{name}", os.path.join(d, name))
    put_file("mavrik-engine", "LICENSE", os.path.join(repo, "LICENSE"))
    patches = sorted(p for p in os.listdir(os.path.join(repo, "patches")) if p.endswith(".patch"))
    put("mavrik-engine", "PATCHES.txt", "Patches applied to the Wine sources, in order (see patches/ in the "
        "repository, and patches/README.md for why each one is there):\n" + "".join(f"  {p}\n" for p in patches))

    # Addons, runtime parts and our own builds.
    put("wine-mono", "COPYING", text_of(paths, "wine-mono-copying"))
    put("wine-gecko", "MPL-2.0.txt", text_of(paths, "spdx-mpl-2.0"))
    put_file("moltenvk", "LICENSE", os.path.join(work, "notices", "MoltenVK-LICENSE"))
    put("moltenvk", "cereal-LICENSE", text_of(paths, "cereal-license"))
    put("moltenvk", "SPIRV-Cross-LICENSE", text_of(paths, "spirv-cross-license"))
    put("moltenvk", "SPIRV-Tools-LICENSE", text_of(paths, "spirv-tools-license"))
    put("dxmt", "LICENSE", text_of(paths, "dxmt-license"))
    put("dxmt", "dxvk.LICENSE", text_of(paths, "dxmt-dxvk-license"))
    put("dxmt", "LLVM-LICENSE.TXT", text_of(paths, "llvm-license"))
    put("dxmt", "LLVM-COPYRIGHT.regex", text_of(paths, "llvm-regex-copyright"))
    convert = text_of(paths, "llvm-convertutf")
    put("dxmt", "LLVM-ConvertUTF-notice.txt", convert[:convert.index("*/", convert.index("Unicode, Inc.")) + 2] + "\n")
    put("dxmt", "DXBCParser-LICENSE-Microsoft", text_of(paths, "dxbcparser-license"))
    put("dxmt", "nvapi-License-NVIDIA.txt", text_of(paths, "nvapi-license"))
    put("dxmt", "README.txt", "DXMT v0.80's files carry code from LLVM 15.0.7 (with its regex and ConvertUTF parts), "
        "Microsoft's DXBCParser, NVIDIA's nvapi headers and DXVK; their notices are in this folder. "
        "winemetal.dll also carries Wine's start-up code (LGPL-2.1-or-later, see ../wine).\n")
    for key in ("gmp", "nettle", "gnutls", "freetype", "sdl2"):
        d = os.path.join(work, "deps", "share", "licences", key)
        for name in sorted(os.listdir(d)):
            put_file(key, name, os.path.join(d, name))
    for project in inputs["media_projects"]:
        put_file("media:" + project, f"{project}.txt", os.path.join(work, "media-notices", project + ".txt"))
    for ref, name in (("spdx-lgpl-2.1", "LGPL-2.1.txt"), ("spdx-lgpl-3.0", "LGPL-3.0.txt"), ("spdx-gpl-2.0", "GPL-2.0.txt"),
                      ("spdx-gpl-3.0", "GPL-3.0.txt"), ("spdx-mpl-1.1", "MPL-1.1.txt"), ("spdx-apache-2.0", "Apache-2.0.txt")):
        put("texts", name, text_of(paths, ref))

    # COMPONENTS.tsv
    rows = []
    for comp in sorted(set(contrib.values()) | {"mavrik-engine", "licences"}):
        if comp.startswith("media:"):
            info = inputs["media_projects"][comp[6:]]
            licence, version, source = info["licence"], info["version"], info["source"]
            files = notices.get(comp, [])
        else:
            licence, _ = COMPONENT_INFO[comp]
            key = SOURCE_KEY.get(comp)
            version = inputs["inputs"][key]["version"] if key else "-"
            source = inputs["inputs"][key]["url"] if key else "https://github.com/camsteinberg/mavrik-engine"
            files = notices.get(comp, [])
            if comp == "licences":
                files = ["COMPONENTS.tsv"]
        rows.append("\t".join([comp, version, licence, source, ",".join(files)]))
    open(os.path.join(lic, "COMPONENTS.tsv"), "w").write(
        "component\tversion\tlicence\tsource\tnotices (in this folder)\n" + "\n".join(rows) + "\n")

    # FILES.tsv: exact paths, with each addon tree collapsed to one pattern.
    entries = dict(contrib)
    entries["build-info.json"] = "mavrik-engine"
    lines = []
    trees = {}
    for path, comp in entries.items():
        parts = path.split("/")
        if comp in ("wine-mono", "wine-gecko") and len(parts) > 4:
            trees.setdefault("/".join(parts[:4]) + "/*", set()).add(comp)
        else:
            lines.append((path, comp))
    for pattern, comps in trees.items():
        if len(comps) != 1:
            sys.exit(f"{pattern} mixes components {comps}")
        lines.append((pattern, comps.pop()))
    lines.append(("licences/*", "licences"))
    lines.sort()
    open(os.path.join(lic, "FILES.tsv"), "w").write(
        "file or pattern\tcomponent\n" + "".join(f"{p}\t{c}\n" for p, c in lines))
    open(os.path.join(lic, "README.txt"), "w").write(
        "This folder lists every part of this engine and its licence.\n\n"
        "COMPONENTS.tsv names each part, its version, its licence, where its source is, and the files in this\n"
        "folder that hold its licence text and copyright notices. FILES.tsv names every file in the engine and\n"
        "the part it belongs to. texts/ holds the full GNU, Mozilla and Apache licence texts the parts refer to.\n\n"
        "The engine is built from CodeWeavers' published CrossOver sources (LGPL). It is not CrossOver.\n"
        "The build recipe and patches: https://github.com/camsteinberg/mavrik-engine\n")
    print(f"licences: {len(rows)} components, {len(lines)} lines in FILES.tsv")


def main(argv):
    if len(argv) == 3 and argv[1] == "media-notices":
        media_notices(argv[2])
    elif len(argv) == 5 and argv[1] == "write":
        write(argv[2], argv[3], argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
