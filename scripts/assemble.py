#!/usr/bin/env python3
"""Turn the Wine install into the engine: one relocatable folder that carries everything.

  assemble.py WORK ENGINE

WORK holds wine-install/ (make install-lib output), deps/ (our Unix libraries), the
GStreamer expansion (gstreamer/), downloads/paths.json, media-notices/ and inputs.json's path in
WORK/inputs.path. ENGINE is created (it must not exist).

What it does, in order:
  1. moves Wine's install into ENGINE and makes sure bin/wine and bin/wineserver exist;
  2. strips the PE half (mingw strip --strip-debug) and the Unix side (strip -x -S);
  3. unpacks Wine Mono and Wine Gecko into share/wine/mono and share/wine/gecko;
  4. copies the Unix libraries Wine opens by name (config.h's SONAME_* values) and everything they
     link into lib/, flat, plus MoltenVK (thinned to x86_64);
  5. adds the media component (scripts/make-media-component.sh) to lib/ and lib/gstreamer-1.0/;
  6. puts DXMT v0.80's 64-bit files in place, exactly as mavrik's s182-fullscreen branch does
     (lib/wine/x86_64-windows/{d3d11,dxgi,d3d10core,winemetal,nvapi64,nvngx}.dll and
     lib/wine/x86_64-unix/winemetal.so, over Wine's own where they exist);
  7. rewrites every load path that points outside the engine to @loader_path or @rpath, removes
     absolute run paths, gives Wine's Unix modules the run path @loader_path/../../ (lib/), and
     signs each changed file ad hoc;
  8. records which component every file came from (WORK/contributions.json) for licences.py.
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
MACHO_MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"}


def run(cmd, **kw):
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def out(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def is_macho(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(4) in MACHO_MAGICS


def load_commands(path):
    """Returns (id, [loads], [rpaths]) for an x86_64 Mach-O file."""
    text = out(["otool", "-l", path])
    ident, loads, rpaths = None, [], []
    cmd = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("cmd "):
            cmd = s.split()[1]
        elif s.startswith("name ") and cmd in ("LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB",
                                                "LC_LAZY_LOAD_DYLIB", "LC_LOAD_UPWARD_DYLIB", "LC_ID_DYLIB"):
            name = s[5:].rsplit(" (offset", 1)[0]
            if cmd == "LC_ID_DYLIB":
                ident = name
            else:
                loads.append(name)
        elif s.startswith("path ") and cmd == "LC_RPATH":
            rpaths.append(s[5:].rsplit(" (offset", 1)[0])
    return ident, loads, rpaths


def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)
        for name in dirnames:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                yield p


class Assembler:
    def __init__(self, work, engine):
        self.work = os.path.abspath(work)
        self.engine = os.path.abspath(engine)
        self.paths = json.load(open(os.path.join(self.work, "downloads", "paths.json")))
        self.inputs = json.load(open(open(os.path.join(self.work, "inputs.path")).read().strip()))
        self.deps = os.path.join(self.work, "deps")
        self.gst = open(os.path.join(self.work, "gst-root.path")).read().strip()
        self.contrib = {}
        self.untouched = set()  # files shipped exactly as their pinned archive has them

    def rel(self, path):
        return os.path.relpath(path, self.engine)

    def mark(self, path, component):
        self.contrib[self.rel(path)] = component

    # 1
    def move_install(self):
        src = os.path.join(self.work, "wine-install", "opt", "mavrik-engine")
        if os.path.exists(self.engine):
            sys.exit(f"{self.engine} already exists")
        shutil.move(src, self.engine)
        for p in walk_files(self.engine):
            self.mark(p, "wine")
        bindir = os.path.join(self.engine, "bin")
        os.makedirs(bindir, exist_ok=True)
        loader = os.path.join(self.engine, "lib", "wine", "x86_64-unix", "wine")
        wine = os.path.join(bindir, "wine")
        if not os.path.lexists(wine):
            if not os.path.isfile(loader):
                sys.exit("no Wine loader in bin/ or lib/wine/x86_64-unix/")
            os.symlink("../lib/wine/x86_64-unix/wine", wine)
            self.mark(wine, "wine")
        if not os.path.exists(os.path.join(bindir, "wineserver")):
            sys.exit("no bin/wineserver")
        print("bin/:", sorted(os.listdir(bindir)))

    # 2
    def strip(self):
        before = int(out(["du", "-sk", self.engine]).split()[0])
        for arch, tool in (("i386-windows", "i686-w64-mingw32-strip"), ("x86_64-windows", "x86_64-w64-mingw32-strip")):
            d = os.path.join(self.engine, "lib", "wine", arch)
            for a in [p for p in walk_files(d) if p.endswith(".a")]:
                os.remove(a)
                self.contrib.pop(self.rel(a), None)
            files = [p for p in walk_files(d) if os.path.isfile(p) and not os.path.islink(p)]
            for i in range(0, len(files), 200):
                subprocess.run([tool, "--strip-debug"] + files[i:i + 200], capture_output=True)
        unix = [p for p in walk_files(os.path.join(self.engine, "lib", "wine", "x86_64-unix")) if is_macho(p)]
        unix += [p for p in walk_files(os.path.join(self.engine, "bin")) if is_macho(p)]
        for p in unix:
            run(["strip", "-x", "-S", p], capture_output=True)
        after = int(out(["du", "-sk", self.engine]).split()[0])
        print(f"stripped: {before // 1024} MB -> {after // 1024} MB")

    # 3
    def addons(self):
        mono_v = self.inputs["inputs"]["wine-mono"]["version"]
        gecko_v = self.inputs["inputs"]["wine-gecko-x86"]["version"]
        share = os.path.join(self.engine, "share", "wine")
        for key, sub, want in (("wine-mono", "mono", f"wine-mono-{mono_v}"),
                               ("wine-gecko-x86", "gecko", f"wine-gecko-{gecko_v}-x86"),
                               ("wine-gecko-x86_64", "gecko", f"wine-gecko-{gecko_v}-x86_64")):
            dest = os.path.join(share, sub)
            os.makedirs(dest, exist_ok=True)
            with tarfile.open(self.paths[key]) as t:
                for m in t.getmembers():
                    if m.name.startswith("/") or ".." in m.name.split("/"):
                        sys.exit(f"{key}: unsafe entry {m.name}")
                t.extractall(dest, filter="tar")
            top = os.path.join(dest, want)
            if not os.path.isdir(top):
                sys.exit(f"{key}: expected {want} in {dest}, found {os.listdir(dest)}")
            for p in walk_files(top):
                self.mark(p, key.replace("-x86_64", "").replace("-x86", ""))
            print(f"{key}: {want}")

    # 4
    def unix_libraries(self):
        config = open(os.path.join(self.work, "wine-install", ".build", "config.h")).read()
        sonames = {}
        for line in config.splitlines():
            if line.startswith("#define SONAME_"):
                parts = line.split(None, 2)
                sonames[parts[1]] = parts[2].strip().strip('"')
        print("Wine opens these by name:", sonames)
        libdir = os.path.join(self.engine, "lib")
        os.makedirs(libdir, exist_ok=True)
        # MoltenVK, thinned to the engine's architecture.
        mvk = tempfile.mkdtemp()
        member = "MoltenVK/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib"
        run(["tar", "-xf", self.paths["moltenvk"], "-C", mvk, member, "MoltenVK/LICENSE"])
        dest = os.path.join(libdir, "libMoltenVK.dylib")
        run(["lipo", "-thin", "x86_64", os.path.join(mvk, member), "-output", dest])
        os.chmod(dest, 0o644)
        self.mark(dest, "moltenvk")
        os.makedirs(os.path.join(self.work, "notices"), exist_ok=True)
        shutil.copy(os.path.join(mvk, "MoltenVK", "LICENSE"), os.path.join(self.work, "notices", "MoltenVK-LICENSE"))
        for define, name in sorted(sonames.items()):
            if name == "libMoltenVK.dylib":
                continue
            if "/" in name:
                sys.exit(f"{define} is a path ({name}); Wine must open its libraries by name")
            if not os.path.exists(os.path.join(self.deps, "lib", name)):
                sys.exit(f"{define} names {name}, which none of our own builds provides")
            self.bundle(name)

    def bundle(self, name):
        libdir = os.path.join(self.engine, "lib")
        dest = os.path.join(libdir, name)
        if os.path.exists(dest):
            return
        src = os.path.realpath(os.path.join(self.deps, "lib", name))
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o644)
        self.mark(dest, self.component_of(name))
        _, loads, _ = load_commands(dest)
        for load in loads:
            base = os.path.basename(load)
            if load.startswith(SYSTEM_PREFIXES):
                continue
            if load.startswith(self.deps) or (load.startswith("@rpath/") and os.path.exists(os.path.join(self.deps, "lib", base))):
                if base != name:
                    self.bundle(base)
                continue
            if load.startswith("@"):
                continue
            sys.exit(f"{name} links {load}, which is outside the engine and outside macOS")

    @staticmethod
    def component_of(name):
        for prefix, comp in (("libgmp", "gmp"), ("libnettle", "nettle"), ("libhogweed", "nettle"),
                             ("libgnutls", "gnutls"), ("libfreetype", "freetype"), ("libSDL2", "sdl2")):
            if name.startswith(prefix):
                return comp
        sys.exit(f"no component is known for {name}; add it to assemble.py and NOTICE.md")

    # 5
    def media(self):
        listing = os.path.join(self.work, "media.tsv")
        run(["bash", os.path.join(os.path.dirname(__file__), "make-media-component.sh"),
             "--from", os.path.join(self.gst, "lib"),
             "--version", self.inputs["inputs"]["gstreamer-runtime"]["version"],
             "--notices", os.path.join(self.work, "media-notices"),
             "--dest", self.engine, "--list", listing])
        for line in open(listing):
            path, licence, project, _ = line.rstrip("\n").split("\t")
            self.contrib[path] = "media:" + project

    # 6
    def dxmt(self):
        pin = self.inputs["inputs"]["dxmt"]
        tmp = tempfile.mkdtemp()
        with tarfile.open(self.paths["dxmt"]) as t:
            t.extractall(tmp, filter="tar")
        root = os.path.join(tmp, "v" + pin["version"])
        for entry, size in pin["files"].items():
            src = os.path.join(root, entry)
            if os.path.getsize(src) != size:
                sys.exit(f"DXMT {entry}: {os.path.getsize(src)} bytes, pinned {size}")
            dest = os.path.join(self.engine, "lib", "wine", entry)
            mode = (os.stat(dest).st_mode & 0o777) if os.path.exists(dest) else 0o644
            if os.path.lexists(dest):
                os.remove(dest)
            shutil.copyfile(src, dest)
            os.chmod(dest, mode)
            self.mark(dest, "dxmt")
            self.untouched.add(self.rel(dest))
            print(f"DXMT {entry}: {size} bytes")

    # 7
    def fix_load_paths(self):
        libdir = os.path.join(self.engine, "lib")
        unixdir = os.path.join(self.engine, "lib", "wine", "x86_64-unix")
        changed = 0
        for path in walk_files(self.engine):
            if not is_macho(path) or self.rel(path) in self.untouched:
                continue
            archs = out(["lipo", "-archs", path]).split()
            if archs != ["x86_64"]:
                sys.exit(f"{self.rel(path)} is {archs}, not x86_64 only")
            ident, loads, rpaths = load_commands(path)
            args = []
            if ident and not ident.startswith("@"):
                args += ["-id", "@rpath/" + os.path.basename(ident)]
            here = os.path.dirname(path)
            for load in loads:
                if load.startswith("@") or load.startswith(SYSTEM_PREFIXES):
                    continue
                base = os.path.basename(load)
                if not os.path.exists(os.path.join(libdir, base)):
                    sys.exit(f"{self.rel(path)} links {load}, which the engine does not carry")
                rel = os.path.relpath(libdir, here)
                args += ["-change", load, "@loader_path/" + base if rel == "." else f"@loader_path/{rel}/{base}"]
            for rp in rpaths:
                if not rp.startswith("@"):
                    args += ["-delete_rpath", rp]
            if os.path.dirname(path) == unixdir and path.endswith(".so") and "@loader_path/../../" not in rpaths:
                args += ["-add_rpath", "@loader_path/../../"]
            if args:
                os.chmod(path, os.stat(path).st_mode | 0o200)
                run(["install_name_tool"] + args + [path], capture_output=True)
                run(["codesign", "-f", "-s", "-", path], capture_output=True)
                changed += 1
        print(f"load paths rewritten in {changed} files")

    def write(self):
        json.dump(self.contrib, open(os.path.join(self.work, "contributions.json"), "w"), indent=1, sort_keys=True)
        print(f"{len(self.contrib)} files recorded")


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    a = Assembler(argv[1], argv[2])
    a.move_install()
    a.strip()
    a.addons()
    a.unix_libraries()
    a.media()
    a.dxmt()
    a.fix_load_paths()
    a.write()


if __name__ == "__main__":
    main(sys.argv)
