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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile


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


def archive_members(paths, key, root, names):
    """{name: bytes} for files root/NAME inside the pinned archive KEY (one pass with tar). Stops the
    build when one is missing."""
    with tempfile.TemporaryDirectory(prefix="notices-") as tmp:
        r = subprocess.run(["tar", "-xf", paths[key], "-C", tmp] + [f"{root}/{n}" for n in names],
                           capture_output=True, text=True)
        found = {n: open(os.path.join(tmp, root, n), "rb").read() for n in names
                 if os.path.isfile(os.path.join(tmp, root, n))}
    missing = [n for n in names if n not in found]
    if missing:
        sys.exit(f"{key}: notices not in the archive: {', '.join(missing)} ({r.stderr.strip()[-300:]})")
    return found


def gecko_notices(inputs, engine):
    """Wine Gecko's own notices (its about:license page), from the engine's copy of omni.ja. omni.ja
    is Mozilla's reordered zip, which unzip reads with a warning (exit 1 or 2); the page is checked
    against the sha256 inputs.json pins."""
    pin = inputs["inputs"]["wine-gecko-x86"]["notices"]
    version = inputs["inputs"]["wine-gecko-x86"]["version"]
    jar = os.path.join(engine, "share", "wine", "gecko", f"wine-gecko-{version}-x86", pin["from"])
    r = subprocess.run(["unzip", "-p", jar, pin["member"]], capture_output=True)
    if r.returncode > 2 or hashlib.sha256(r.stdout).hexdigest() != pin["sha256"]:
        sys.exit(f"Wine Gecko's {pin['member']} from {jar}: exit {r.returncode}, sha256 "
                 f"{hashlib.sha256(r.stdout).hexdigest()}, pinned {pin['sha256']}")
    return r.stdout


def patch_credits(patch_file):
    """(where the patch comes from, what it does), from its header."""
    header = open(patch_file, encoding="utf-8").read().split("\n--- a/", 1)[0]
    paragraphs = [p.strip() for p in header.split("\n\n") if p.strip()]
    if paragraphs and paragraphs[0].startswith("Adopted from"):
        origin = " ".join(paragraphs[0].split()).replace(" Its own header follows.", "")
        return origin, paragraphs[1].splitlines()[0] if len(paragraphs) > 1 else ""
    return "this repository (https://github.com/camsteinberg/mavrik-engine)", paragraphs[0].splitlines()[0] if paragraphs else ""


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
    "gnutls": ("LGPL-2.1-or-later (includes libtasn1: LGPL-2.1-or-later, libunistring: LGPL-3.0-or-later OR GPL-2.0-or-later, "
               "CRYPTOGAMS: BSD-style, inih: BSD-3-Clause, crypto-auditing: MIT)", "GnuTLS, Wine's TLS"),
    "freetype": ("FTL (its BDF and PCF drivers: X11-style notices)", "FreeType, Wine's font rendering"),
    "sdl2": ("Zlib (includes HIDAPI under its BSD terms, and yuv2rgb: BSD-3-Clause)", "SDL2, Wine's game controller support"),
    "mavrik-engine": ("LGPL-2.1-or-later", "this repository's build files and build record"),
    "licences": ("(the licence texts themselves)", "this folder"),
}
# Where each component's source is (an input, or a release source).
SOURCE_KEY = {"wine": "crossover-sources", "wine-mono": "wine-mono-source", "wine-gecko": "wine-gecko-source",
              "moltenvk": "moltenvk", "dxmt": "dxmt-source", "gmp": "gmp", "nettle": "nettle", "gnutls": "gnutls",
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
        folder = component.replace("media:", "media/")
        p = os.path.join(lic, folder, name)
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
    lines = ["Patches applied to the Wine sources, in order. Each is in patches/ in the repository",
             "(https://github.com/camsteinberg/mavrik-engine), with patches/README.md saying why it is there.", ""]
    for name in patches:
        origin, what = patch_credits(os.path.join(repo, "patches", name))
        lines += [name, f"  {what}", f"  From: {origin}", ""]
    put("mavrik-engine", "PATCHES.txt", "\n".join(lines))

    # Addons, runtime parts and our own builds.
    mono = inputs["inputs"]["wine-mono-source"]
    for name, data in sorted(archive_members(paths, "wine-mono-source", mono["notices_root"], mono["notices"]).items()):
        put("wine-mono", name, data)
    put("wine-mono", "README.txt", "Wine Mono's notices: COPYING says how its parts are licensed, and the other files are "
        "the licence and notice files of each project it is built from (Mono and the projects in mono/external, FNA, "
        "FAudio, FNA3D, MojoShader, SDL3, SDL2-CS and SDL3-CS, winforms, WPF, monoDX), as they are in Wine Mono's "
        f"source ({mono['url']}).\n")
    put("wine-gecko", "MPL-2.0.txt", text_of(paths, "spdx-mpl-2.0"))
    put("wine-gecko", "license.html", gecko_notices(inputs, engine))
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
        for dirpath, _, files in sorted(os.walk(d)):
            for name in sorted(files):
                src = os.path.join(dirpath, name)
                put_file(key, os.path.relpath(src, d), src)
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
            pinned = (inputs["inputs"].get(key) or inputs["release_sources"][key]) if key else None
            version = pinned["version"] if key else "-"
            if comp == "wine":
                wine_version = open(os.path.join(work, "wine-src", "VERSION")).read().strip().replace("Wine version ", "")
                version = f"{wine_version} (CrossOver {version} sources)"
            source = pinned["url"] if key else "https://github.com/camsteinberg/mavrik-engine"
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
