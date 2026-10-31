#!/usr/bin/env python3
"""The engine's gates: checks that fail the build.

  gates.py addons-source ADDONS_C INPUTS      stop if addons.c names a Mono or Gecko version we have not pinned
  gates.py run ENGINE WORK                    run every gate on the built engine
  gates.py selftest ENGINE WORK               show that every gate fails on a bad input

WORK is the build's work folder (wine-src/, inputs.path, the masked build paths). Results go to
WORK/gates/results.json and to the job summary when GITHUB_STEP_SUMMARY is set.

The gates:
  relocatable   every Mach-O file: no load path, id or run path outside /usr/lib and /System
                that is absolute; every file is x86_64 only
  dlopen        every bundled library loads on this machine with the build's own install
                folders moved away, and nothing loads from outside the engine and macOS
  pe32          the 32-bit Windows half is there: syswow64's ntdll.dll is a 32-bit PE, with
                hundreds of files beside it
  winemac       winemac.so exports macdrv_functions, and its layout gives DXMT what DXMT reads
                (the fallback names DXMT would use without it are reported)
  addons        Wine Mono and Gecko are in the engine at exactly the versions addons.c names
  wine          wine --version prints the expected version; wineboot --init in a fresh prefix
                finishes with no Mono or Gecko download prompt and finds the engine's Mono; Wine
                Gecko loads from the engine in the 64-bit and the 32-bit half; in both halves,
                Wine's own code uses GnuTLS, MoltenVK and FreeType and loads its GStreamer and
                FFmpeg modules (tools/winelibs.c), every library Wine opens by name is loaded from
                the engine, and no Wine process loads anything from outside the engine and macOS
  fonts         wineboot --init in a fresh prefix puts wine.inf's FontFiles (patch 0017) into
                C:\\windows\\Fonts, each the same bytes as its source in share/wine/fonts; a file
                already there is kept through wineboot --update (COPYFLG_NO_OVERWRITE, patch 0016)
  media         GStreamer and FFmpeg load from inside the engine, never from
                /Library/Frameworks/GStreamer.framework, and build the elements Wine uses. A Mac
                that has the framework is not changed: every library dyld loads and every plugin
                file must still be inside the engine, which is the case that matters on a
                player's Mac with GStreamer installed
  licences      every file in the engine is covered by a line in licences/FILES.tsv, and every
                component has its licence texts
  nogpl         no GPL-only file in the media component
  identity      the engine never presents itself as CrossOver or sends anyone to CodeWeavers: the
                loader's Info.plist has the engine's own identifier, and no text in Wine's files
                names CrossOver or CodeWeavers outside a reviewed list of names no player sees
                (copyright lines, log lines, internal registry keys)
  buildpaths    no file carries the build machine's work or recipe folder (compiled-in paths, debug
                maps, source paths)
  dxmt          DXMT's seven files are the ones build-dxmt.sh made from the pinned source at the pinned
                commit with this repository's dxmt/patches (build-info.json's record, file by file);
                d3d11.dll carries the version string <commit>-mavrik.<patches>; winemetal.dll exports the
                pinned number of names, with patch 0002's MetalDrawable_signalEventWhenPresented, which
                d3d11.dll imports; winemetal.so's macOS target is the pinned one; none of the seven files
                names the work folder, the recipe or the home folder
  d3d11         a Windows program draws through Direct3D 11 on a visible window: DXMT's device,
                60 frames presented into its Metal view, 120 more under vsync (SyncInterval 1) at 50
                or more a second with no "not presented within" line from DXMT (patch 0002's 100 ms
                valve) while DXMT's log does reach the output ("Using feature level"), and a GPU
                readback; winemetal.so and
                winemac.so load from the engine. A machine with no Metal device (GitHub's Intel
                runners are virtual machines without one) reports SKIP, never PASS
  playback      a Windows program decodes a movie (H.264 and AAC in MP4) in both halves through Media
                Foundation and through the Windows Media reader; GStreamer's plugins load from the
                engine's lib/gstreamer-1.0, and nothing from outside the engine and macOS
  steamredirect Valve's Steam bridge in the loader (patch 0004): in both halves, a Windows program loads
                a DLL named steamclient64.dll or steamclient.dll, and its export jumps into the
                lsteamclient.dll beside it (tools/steamprobe.c builds all three). No Steam needed
  dockname      a Windows program started with WINEPRELOADERAPPNAME shows a window and starts a 32-bit
                child that shows its own; for both, LaunchServices (the Dock and the app switcher,
                patch 0006, read with lsappinfo) and the window server (the menu bar and Cmd-Tab,
                patch 0007, its owner name read with CGWindowListCopyWindowInfo) show that name, not
                "wine", for a plain title, one with '&', '<' and '>', and one with accented, CJK and
                emoji characters; a CJK title past 31 bytes is cut between whole characters, '/' shows
                as U+2215 in the window server, and a title "Control" still starts the program, not
                Wine's control panel; each program's executable (proc_pidpath) is the loader inside the
                engine's mavrik.app (patch 0037), so inside the engine too; a program started with no link
                (a title no link can carry, "..", or no title and an argv[0] that is not UTF-8) still
                starts and shows the bundle's name, "mavrik", never "wine"; and with no title the 32-bit
                child keeps its own name. The executable path is checked
                as proc_pidpath gives it, without resolving links. Gates run outside a login (Aqua)
                session report SKIP
  controllers   game controllers through patch 0035's virtual pad (MAVRIK_PAD_VIRTUAL), each case in its own
                wineserver session of one fresh prefix (winedevice reads the pad variables when the session
                starts): tools/gamepadprobe.c's selftest passes all 18 checks (XInput, rumble held and stopped,
                the wired battery, DirectInput, raw input, Windows.Gaming.Input, unplug and replug) in both
                halves with the pad as an Xbox 360 pad (045e:028e), a DualShock 4 (054c:09cc), a DualSense
                (054c:0ce6) and a Switch Pro Controller (057e:2009, by position); and with MAVRIK_PAD_HIDRAW=1
                each PlayStation id is no XInput pad and no DirectInput controller (selftest absent)
  gamemode      the loader bundle lib/wine/x86_64-unix/mavrik.app that patch 0037 starts every Windows program
                from: its Info.plist has exactly assemble.py's keys (the games category, LSSupportsGameMode and
                GCSupportsGameMode, LSUIElement, CFBundleExecutable wine, the Local Network usage text, no
                document types), Contents/MacOS/wine is the engine's loader (the same file with the bundle's
                signature taken off), and the bundle's ad hoc signature verifies (codesign --verify --strict),
                so its Info.plist is sealed. That a Windows program's process runs from it is the dockname
                gate's check

A gate returns PASS, FAIL or, for d3d11 and dockname only, SKIP with its reason.

Every Wine run has the Mac display driver off (Wine's null driver, as mavrik makes and updates a prefix),
so no window or prompt can reach the screen, except the d3d11 and dockname probes, which must draw;
their prefixes are still made with it off. Every Wine step has a bound, and whatever a prefix started
ends with its gate: wineserver -k with a bound, then SIGKILL to each of the prefix's processes still
running, checked; a process left over fails the gate.

macOS's syspolicyd checks each new program before it runs, and the program waits while syspolicyd is
down. When it crashes over and over, launchd restarts it later each time (up to 20 minutes), so the gates
stop at the first syspolicyd crash report written while they run, instead of starting more programs that
would wait on it (S213: run 3's wine gate, and the Mac at its lock screen after).
"""
import ctypes
import fcntl
import fnmatch
import glob
import signal
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata

from assemble import (LOADER_BUNDLE, LOADER_BUNDLE_EXE, NOT_CARRIED, OPENED_BY, loader_bundle_plist,
                      sha256 as sha256_file)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
MACHO_MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"}
GST_FRAMEWORK = "/Library/Frameworks/GStreamer.framework"
# The elements Wine's media code builds pipelines from, and the decoders for the formats games ship.
GST_ELEMENTS = ["appsrc", "appsink", "decodebin", "typefind", "queue", "videoconvert", "videoscale",
                "audioconvert", "audioresample", "videoflip", "deinterlace", "volume", "qtdemux",
                "matroskademux", "oggdemux", "avidemux", "asfdemux", "wavparse", "mpegpsdemux",
                "tsdemux", "id3demux", "mpegaudioparse", "h264parse", "vorbisdec", "theoradec",
                "opusdec", "flacdec", "mpg123audiodec", "avdec_h264", "avdec_aac", "avdec_wmv3",
                "avdec_wmav2", "avdec_mpeg4"]
FFMPEG_DECODERS = ["h264", "aac", "mp3float", "wmv3", "wmav2", "mpeg4", "vp9"]
GPL_NAMES = ("x264", "x265", "a52", "dvdread", "dvdnav", "openh264", "mpeg2dec", "libmpeg2", "dtsdec",
             "libdca", "faad", "postproc", "lame", "twolame", "sidplay", "cdio")


# ---------------------------------------------------------------- helpers

def out(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def is_macho(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(4) in MACHO_MAGICS


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            yield os.path.join(dirpath, name)
        for name in dirnames:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                yield p


def macho_paths(path):
    """[(kind, value)] for every load path, id and run path in a Mach-O file (all architectures)."""
    text = out(["otool", "-l", path]).stdout
    found, cmd = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("cmd "):
            cmd = s.split()[1]
        elif s.startswith("name ") and cmd and "DYLIB" in cmd or (s.startswith("name ") and cmd == "LC_LOAD_DYLINKER"):
            found.append((cmd, s[5:].rsplit(" (offset", 1)[0]))
        elif s.startswith("path ") and cmd == "LC_RPATH":
            found.append((cmd, s[5:].rsplit(" (offset", 1)[0]))
    return found


def stale(exe, src):
    return not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src)


def compile_tool(work, name, frameworks=()):
    src = os.path.join(REPO, "tools", name + ".c")
    if not os.path.exists(src):
        src = os.path.join(REPO, "tools", name + ".m")
    exe = os.path.join(work, "tools", name)
    if stale(exe, src):
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        fw = [a for f in frameworks for a in ("-framework", f)]
        subprocess.run(["clang", "-O1", "-arch", "x86_64", "-o", exe, src] + fw, check=True)
    return exe


PE_COMPILERS = {"64": "x86_64-w64-mingw32-gcc", "32": "i686-w64-mingw32-gcc"}


def compile_pe_tool(work, name, bits, libs, extra=()):
    """A Windows program from tools/NAME.c for one half of Wine (bits "64" or "32")."""
    src = os.path.join(REPO, "tools", name + ".c")
    exe = os.path.join(work, "tools", f"{name}{bits}.exe")
    if stale(exe, src):
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        subprocess.run([PE_COMPILERS[bits], "-O1", "-s"] + list(extra) + ["-o", exe, src] + [f"-l{l}" for l in libs], check=True)
    return exe


def dyld_images(stderr):
    images = []
    for line in stderr.splitlines():
        m = re.match(r"dyld\[\d+\]: (?:<[^>]*> )?(/.*)$", line)
        if m:
            images.append(m.group(1).strip())
    return images


def outside(images, engine, allowed=()):
    """The loaded images that are neither macOS's nor inside the engine (paths compared resolved)."""
    roots = [os.path.realpath(engine).rstrip("/") + "/"]
    allowed = [os.path.realpath(a) for a in allowed]
    bad = []
    for img in images:
        if img.startswith(SYSTEM_PREFIXES):
            continue
        real = os.path.realpath(img)
        if any(real.startswith(r) for r in roots) or real in allowed:
            continue
        bad.append(img)
    return sorted(set(bad))


# ---------------------------------------------------------------- gates

def gate_relocatable(engine, ctx):
    problems, count = [], 0
    for path in walk(engine):
        if not is_macho(path):
            continue
        count += 1
        rel = os.path.relpath(path, engine)
        archs = out(["lipo", "-archs", path]).stdout.split()
        if archs != ["x86_64"]:
            problems.append(f"{rel}: architectures {archs}")
        for kind, value in macho_paths(path):
            if kind == "LC_LOAD_DYLINKER":
                continue
            if not value.startswith("/") or value.startswith(SYSTEM_PREFIXES):
                continue
            problems.append(f"{rel}: {kind} {value}")
    if count == 0:
        problems.append("no Mach-O files found")
    return not problems, f"{count} Mach-O files swept", problems


def gate_dlopen(engine, ctx):
    libs = sorted(p for p in walk(os.path.join(engine, "lib")) if p.endswith(".dylib") and not os.path.islink(p)
                  and os.path.relpath(p, engine).count("/") <= 2)
    if not libs:
        return False, "no bundled libraries", ["nothing to load"]
    exe = compile_tool(ctx["work"], "dlcheck")
    masked = []
    try:
        for d in ctx.get("mask", []):
            if os.path.exists(d):
                os.rename(d, d + ".masked")
                masked.append(d)
        with tempfile.TemporaryDirectory(prefix="dlopen-") as home:
            env = {"PATH": "/usr/bin:/bin", "HOME": home, "DYLD_PRINT_LIBRARIES": "1",
                   "DYLD_FALLBACK_LIBRARY_PATH": "/usr/lib"}
            r = out([exe] + libs, env=env, timeout=600)
    finally:
        for d in masked:
            os.rename(d + ".masked", d)
    problems = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    problems += [f"loaded from outside the engine: {p}" for p in outside(dyld_images(r.stderr), engine, [exe])]
    if r.returncode and not problems:
        problems.append(f"dlcheck exited {r.returncode}")
    return not problems, f"{len(libs)} libraries loaded with {len(masked)} build folders masked", problems


def pe_machine(path):
    with open(path, "rb") as f:
        data = f.read(4096)
    if data[:2] != b"MZ":
        return None, None
    off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[off:off + 4] != b"PE\0\0":
        return None, None
    machine = struct.unpack_from("<H", data, off + 4)[0]
    magic = struct.unpack_from("<H", data, off + 24)[0]
    return machine, magic


def gate_pe32(engine, ctx):
    d32 = os.path.join(engine, "lib", "wine", "i386-windows")
    ntdll = os.path.join(d32, "ntdll.dll")
    problems = []
    if not os.path.isfile(ntdll):
        return False, "no 32-bit half", [f"missing {os.path.relpath(ntdll, engine)}"]
    machine, magic = pe_machine(ntdll)
    if machine != 0x14C or magic != 0x10B:
        problems.append(f"i386-windows/ntdll.dll is machine {machine and hex(machine)}, optional header {magic and hex(magic)}, not a 32-bit PE")
    files = [p for p in walk(d32) if os.path.isfile(p)]
    if len(files) < 300:
        problems.append(f"only {len(files)} files in i386-windows")
    debug = []
    for name in ("ntdll.dll", "kernelbase.dll", "user32.dll"):
        for arch in ("i386-windows", "x86_64-windows"):
            p = os.path.join(engine, "lib", "wine", arch, name)
            if os.path.isfile(p) and b".debug_info" in open(p, "rb").read():
                debug.append(f"{arch}/{name}")
    if debug:
        problems.append("not stripped: " + ", ".join(debug))
    return not problems, f"ntdll.dll is a 32-bit PE ({os.path.getsize(ntdll)} bytes), {len(files)} files in i386-windows", problems


def struct_fields(source, name):
    """Field names of `struct NAME { ... };` in C source, in order."""
    m = re.search(r"struct\s+" + re.escape(name) + r"\s*\{(.*?)\};", source, re.S)
    if not m:
        return None
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", m.group(1), flags=re.S)
    fields = []
    for decl in body.split(";"):
        decl = decl.strip()
        if not decl:
            continue
        fp = re.search(r"\(\s*(?:WINAPI\s*)?\*\s*(\w+)\s*\)", decl)
        if fp:
            fields.append(fp.group(1))
            continue
        decl = re.sub(r"\[.*?\]|:\s*\d+$", "", decl).strip()
        fields.append(re.findall(r"\w+", decl)[-1])
    return fields


def winemac_check(winemac_so, cx_source, dxmt_source):
    problems, notes = [], []
    syms = out(["nm", "-gU", winemac_so]).stdout.split()
    if "_macdrv_functions" not in syms:
        problems.append("winemac.so does not export _macdrv_functions")
    dx = open(dxmt_source).read()
    fallbacks = [n for n in re.findall(r'dlsym\(RTLD_DEFAULT,\s*"(\w+)"\)', dx) if n != "macdrv_functions"]
    fallbacks = list(dict.fromkeys(fallbacks))
    exported = [n for n in fallbacks if "_" + n in syms]
    notes.append(f"DXMT's fallback names ({', '.join(fallbacks)}): {len(exported)} of {len(fallbacks)} exported")
    cx = open(cx_source).read()
    want = struct_fields(dx, "macdrv_functions_t")
    have = struct_fields(cx, "macdrv_functions_t")
    if not want or not have or have[:len(want)] != want:
        problems.append(f"macdrv_functions layout differs: DXMT reads {want}, the engine has {have and have[:len(want or [])]}")
    want_w = struct_fields(dx, "macdrv_win_data")
    have_w = struct_fields(cx, "d3dmetal_macdrv_win_data")
    if not want_w or not have_w or have_w[:len(want_w)] != want_w:
        problems.append(f"window data layout differs: DXMT reads {want_w}, the engine gives {have_w and have_w[:len(want_w or [])]}")
    if problems and len(exported) == len(fallbacks) and fallbacks:
        problems = []  # DXMT would bind through the fallback names instead
        notes.append("macdrv_functions unusable, but every fallback name is exported")
    return problems, notes


def dxmt_winemetal_source(ctx):
    """The winemetal_unix.c DXMT was built from, patches applied (build-dxmt.sh keeps it)."""
    return os.path.join(ctx["work"], "dxmt-install", ".build", "winemetal_unix.c")


def gate_winemac(engine, ctx):
    so = os.path.join(engine, "lib", "wine", "x86_64-unix", "winemac.so")
    cx = os.path.join(ctx["work"], "wine-src", "dlls", "winemac.drv", "d3dmetal.c")
    problems, notes = winemac_check(so, cx, dxmt_winemetal_source(ctx))
    dxmt = ctx["inputs"]["inputs"]["dxmt-source"]["version"]
    return not problems, "; ".join([f"_macdrv_functions exported, layout matches DXMT {dxmt}"] + notes) if not problems else "; ".join(notes), problems


# ---------------------------------------------------------------- dxmt

# The export patch 0002 adds to winemetal.dll, which d3d11.dll must import.
DXMT_PRESENTED_EXPORT = "MetalDrawable_signalEventWhenPresented"


def pe_exports(path):
    """The names a PE file exports (mingw objdump's name pointer table)."""
    text = out(["x86_64-w64-mingw32-objdump", "-p", path]).stdout
    m = re.search(r"\[Ordinal/Name Pointer\] Table.*?\n(.*?)(?:\n\s*\n|\Z)", text, re.S)
    return re.findall(r"^\s*\[\s*\d+\]\s+\+base\[\s*\d+\]\s+[0-9a-f]+\s+(\S+)\s*$", m.group(1), re.M) if m else []


def pe_imports(path, dll):
    """The names a PE file imports from dll."""
    text = out(["x86_64-w64-mingw32-objdump", "-p", path]).stdout
    m = re.search(r"DLL Name: " + re.escape(dll) + r"\n.*?\n(.*?)(?:\n\s*\n|\Z)", text, re.S | re.I)
    return re.findall(r"^\s*[0-9a-f]+\s+\S+\s+[0-9a-f]+\s+(\S+)", m.group(1), re.M) if m else []


def macho_minos(path):
    m = re.search(r"cmd LC_BUILD_VERSION.*?minos (\S+)", out(["otool", "-l", path]).stdout, re.S)
    return m.group(1) if m else None


def dxmt_check(engine, ctx):
    """(problems, notes): the engine's DXMT files are the ones build-dxmt.sh made from the pinned source and
    this repository's patches, with the version string, the export patch 0002 adds, the macOS target and
    no build path."""
    pin = ctx["inputs"]["inputs"]["dxmt-source"]
    problems = []
    try:
        rec = json.load(open(os.path.join(engine, "build-info.json")))["dxmt"]
    except (OSError, KeyError, ValueError) as e:
        return [f"build-info.json has no DXMT record ({e})"], []
    if rec.get("commit") != pin["commit"]:
        problems.append(f"built from DXMT {rec.get('commit')}, pinned {pin['commit']}")
    pdir = os.path.join(REPO, "dxmt", "patches")
    have = [{"file": p, "sha256": sha256_file(os.path.join(pdir, p))} for p in sorted(os.listdir(pdir)) if p.endswith(".patch")]
    if rec.get("patches") != have:
        problems.append(f"built with patches {rec.get('patches')}, the recipe has {have}")
    lib = os.path.join(engine, "lib", "wine")
    for f in pin["files"]:
        path = os.path.join(lib, f)
        if not os.path.isfile(path):
            problems.append(f"lib/wine/{f} is missing")
        elif sha256_file(path) != rec.get("files", {}).get(f):
            problems.append(f"lib/wine/{f} is not the file build-dxmt.sh made")
    version = f"{pin['commit'][:10]}-mavrik.{len(have)}"
    if rec.get("version_string") != version:
        problems.append(f"version string {rec.get('version_string')}, expected {version}")
    d3d11 = os.path.join(lib, "x86_64-windows", "d3d11.dll")
    if os.path.isfile(d3d11) and version.encode() not in open(d3d11, "rb").read():
        problems.append(f"d3d11.dll does not carry the version string {version}")
    winemetal = os.path.join(lib, "x86_64-windows", "winemetal.dll")
    exports = pe_exports(winemetal) if os.path.isfile(winemetal) else []
    if len(exports) != pin["winemetal_exports"] or DXMT_PRESENTED_EXPORT not in exports:
        problems.append(f"winemetal.dll exports {len(exports)} names "
                        f"({'with' if DXMT_PRESENTED_EXPORT in exports else 'without'} {DXMT_PRESENTED_EXPORT}), "
                        f"pinned {pin['winemetal_exports']} with it")
    if os.path.isfile(d3d11) and DXMT_PRESENTED_EXPORT not in pe_imports(d3d11, "winemetal.dll"):
        problems.append(f"d3d11.dll does not import {DXMT_PRESENTED_EXPORT} from winemetal.dll")
    so = os.path.join(lib, "x86_64-unix", "winemetal.so")
    minos = macho_minos(so) if os.path.isfile(so) else None
    if minos != pin["deployment_target"]:
        problems.append(f"winemetal.so needs macOS {minos}, pinned {pin['deployment_target']}")
    needles = build_paths(ctx) + [os.path.expanduser("~")]
    for f in pin["files"]:
        path = os.path.join(lib, f)
        if os.path.isfile(path):
            data = open(path, "rb").read()
            hits = [n for n in needles if n.encode() in data]
            if hits:
                problems.append(f"lib/wine/{f} contains {', '.join(hits)}")
    notes = [f"DXMT {pin['commit'][:10]} from its pinned source with {', '.join(p['file'] for p in have)}",
             f"version {version} in d3d11.dll", f"winemetal.dll exports {len(exports)} names with {DXMT_PRESENTED_EXPORT}, "
             f"which d3d11.dll imports", f"winemetal.so needs macOS {minos}", "no build or home path in its 7 files"]
    return problems, notes


def gate_dxmt(engine, ctx):
    problems, notes = dxmt_check(engine, ctx)
    return not problems, "; ".join(notes), problems


def addons_versions(addons_c):
    text = open(addons_c).read()
    mono = re.search(r'#define MONO_VERSION "([^"]+)"', text)
    gecko = re.search(r'#define GECKO_VERSION "([^"]+)"', text)
    return (mono and mono.group(1)), (gecko and gecko.group(1))


def addons_source_problems(addons_c, inputs):
    mono, gecko = addons_versions(addons_c)
    pins = inputs["inputs"]
    problems = []
    if mono != pins["wine-mono"]["version"]:
        problems.append(f"addons.c asks for Wine Mono {mono}; inputs.json pins {pins['wine-mono']['version']}")
    for arch in ("x86", "x86_64"):
        if gecko != pins["wine-gecko-" + arch]["version"]:
            problems.append(f"addons.c asks for Wine Gecko {gecko}; inputs.json pins {pins['wine-gecko-' + arch]['version']} ({arch})")
    return problems, mono, gecko


def gate_addons(engine, ctx):
    addons_c = os.path.join(ctx["work"], "wine-src", "dlls", "appwiz.cpl", "addons.c")
    problems, mono, gecko = addons_source_problems(addons_c, ctx["inputs"])
    for d in (f"share/wine/mono/wine-mono-{mono}", f"share/wine/gecko/wine-gecko-{gecko}-x86",
              f"share/wine/gecko/wine-gecko-{gecko}-x86_64"):
        p = os.path.join(engine, d)
        n = sum(1 for _ in walk(p)) if os.path.isdir(p) else 0
        if n < 10:
            problems.append(f"{d}: {n} files")
    return not problems, f"Wine Mono {mono} and Gecko {gecko} (x86, x86_64), as addons.c names", problems


# Wine's Mac display driver off: Wine falls back to its null driver, where no window reaches the screen
# (mavrik's PREFIX_BUILD_DLL_OVERRIDES, wine_session.rs).
DISPLAY_OFF = {"WINEDLLOVERRIDES": "winemac.drv=d"}


def wine_env(engine, home, display=False):
    """Wine's environment for a gate's prefix in home; the Mac display driver only when display is True."""
    # GStreamer's plugin list goes in this home, as the README asks of any program that starts the engine.
    env = {"PATH": f"{engine}/bin:/usr/bin:/bin", "HOME": home, "WINEPREFIX": os.path.join(home, "prefix"),
           "WINEDEBUG": "fixme-all,+mscoree,+appwizcpl", "LANG": "en_US.UTF-8", "TMPDIR": home,
           "GST_REGISTRY_1_0": os.path.join(home, "gst-registry.bin"), "WINEARCH": "wow64"}
    return env if display else dict(env, **DISPLAY_OFF)


def with_display(env):
    """env with the Mac display driver back on, for a probe that must draw."""
    return {k: v for k, v in env.items() if k not in DISPLAY_OFF}


# ---------------------------------------------------------------- ending a prefix's processes

_libproc = None


def _proc():
    global _libproc
    if _libproc is None:
        _libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    return _libproc


def all_pids():
    lib = _proc()
    n = lib.proc_listallpids(None, 0)
    buf = (ctypes.c_int * (n + 256))()
    n = lib.proc_listallpids(buf, ctypes.sizeof(buf))
    return [p for p in buf[:max(n, 0)] if p > 0]


def pid_path(pid):
    buf = ctypes.create_string_buffer(4096)
    n = _proc().proc_pidpath(pid, buf, ctypes.sizeof(buf))
    return buf.value.decode("utf-8", "replace") if n > 0 else None


def pid_env_value(pid, name):
    """name's value in pid's environment (sysctl KERN_PROCARGS2), or None where macOS doesn't show it."""
    libc = ctypes.CDLL(None)
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(0)
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    # argc, the executable path, then argv and the environment. Wine rewrites argv in place to the
    # Windows command line, so argc can't be trusted to find where the environment starts: the
    # strings after the executable path are searched for NAME= instead.
    key = name.encode() + b"="
    for item in buf.raw[4:size.value].split(b"\0")[1:]:
        if item.startswith(key):
            return item[len(key):].decode("utf-8", "replace")
    return None


def server_lock_owner(prefix):
    """The pid of the server running for prefix (the owner of the lock in Wine's server folder,
    /tmp/.wine-<uid>/server-<dev>-<inode>), as wineserver -k finds it, or None."""
    try:
        st = os.stat(prefix)
        fd = os.open(f"/tmp/.wine-{os.getuid()}/server-{st.st_dev:x}-{st.st_ino:x}/lock", os.O_RDONLY)
    except OSError:
        return None
    try:
        got = fcntl.fcntl(fd, fcntl.F_GETLK, struct.pack("qqihh", 0, 0, 0, fcntl.F_WRLCK, 0))
        _, _, pid, kind, _ = struct.unpack("qqihh", got)
        return pid if kind != fcntl.F_UNLCK and pid > 0 else None
    except OSError:
        return None
    finally:
        os.close(fd)


def prefix_processes(engine, prefix):
    """The processes running a program from engine that belong to prefix: its server, and every
    process whose WINEPREFIX names it (Wine's programs keep it in their environment)."""
    root = os.path.realpath(engine).rstrip("/") + "/"
    want = os.path.realpath(prefix)
    try:
        st = os.stat(prefix)
        same = lambda p: os.path.realpath(p) == want or (lambda s: (s.st_dev, s.st_ino) == (st.st_dev, st.st_ino))(os.stat(p))
    except OSError:
        same = lambda p: os.path.realpath(p) == want
    server = server_lock_owner(prefix)
    found = []
    for pid in all_pids():
        if pid <= 1 or pid == os.getpid():
            continue
        path = pid_path(pid)
        if not path or not os.path.realpath(path).startswith(root):
            continue
        value = pid_env_value(pid, "WINEPREFIX")
        try:
            mine = pid == server or (value is not None and same(value))
        except OSError:
            mine = False
        if mine:
            found.append(pid)
    return found


def end_prefix(engine, env, bound=30):
    """Ends everything the prefix in env started: wineserver -k within bound seconds, then SIGKILL to
    each of the prefix's processes still running (up to five passes), then a check that none is left.
    Never raises. Returns the problems: wineserver -k not returning, any process it left, any process
    still there after SIGKILL."""
    prefix = env["WINEPREFIX"]
    problems = []
    try:
        subprocess.run([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, capture_output=True, timeout=bound)
    except subprocess.TimeoutExpired:
        problems.append(f"wineserver -k did not return in {bound} s")
    except OSError as e:
        problems.append(f"wineserver -k could not start: {e}")
    left, killed = [], set()
    try:
        for _ in range(5):
            left = prefix_processes(engine, prefix)
            if not left:
                break
            for pid in left:
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed.add(pid)
                except ProcessLookupError:
                    pass
            time.sleep(0.2)
        deadline = time.time() + 10
        while left and time.time() < deadline:
            time.sleep(0.25)
            left = prefix_processes(engine, prefix)
    except Exception as e:  # the listing must never hide the gate's own result
        problems.append(f"the prefix's processes could not be listed: {e!r}")
    if killed:
        problems.append(f"{len(killed)} of the prefix's Wine processes were still running after wineserver -k "
                        f"(ended with SIGKILL: {sorted(killed)})")
    if left:
        problems.append(f"the prefix's Wine processes {left} were still running after SIGKILL")
    return problems


def settle(engine, env, step, bound=300):
    """Waits for the prefix's server to exit (wineserver -w) within bound seconds. Returns the problems:
    a step left waiting (for a window's answer, or on a program that never started)."""
    try:
        subprocess.run([os.path.join(engine, "bin", "wineserver"), "-w"], env=env, capture_output=True, timeout=bound)
        return []
    except subprocess.TimeoutExpired:
        return [f"{step}: Wine's processes were still running after {bound} s"]


# ---------------------------------------------------------------- macOS's syspolicyd

CRASH_REPORTS = "/Library/Logs/DiagnosticReports"


def syspolicyd_watch():
    """Prints, once per run, whether the syspolicyd stop can see crash reports. Where the folder can't be
    read (a GitHub runner, an account outside its group), the stop is off and the output says so."""
    if os.access(CRASH_REPORTS, os.R_OK | os.X_OK):
        print(f"syspolicyd stop: on (reads {CRASH_REPORTS})", flush=True)
    else:
        print(f"syspolicyd stop: OFF, {CRASH_REPORTS} can't be read here, so a syspolicyd crash during the run "
              "would not stop it", flush=True)


# Folders Wine ran programs from (engine clones, patch 0007's link folders): removed only when the whole run
# ends (remove_later, then remove_deferred), because syspolicyd checks each new program while it runs and
# crashes when the file is gone before it gets to it (S213).
_DEFERRED = []


def remove_later(path):
    if path not in _DEFERRED:
        _DEFERRED.append(path)


def remove_deferred():
    while _DEFERRED:
        shutil.rmtree(_DEFERRED.pop(), ignore_errors=True)


def syspolicyd_crashes(since):
    """The syspolicyd crash reports written since the time since (seconds), oldest first ([] where the
    folder can't be read; syspolicyd_watch says so at the start of the run)."""
    try:
        reports = [p for p in glob.glob(os.path.join(CRASH_REPORTS, "syspolicyd-*.ips")) if os.path.getmtime(p) >= since]
    except OSError:
        return []
    return sorted(reports, key=os.path.getmtime)


# appwiz.cpl traces "Got URL" just before it opens a Mono or Gecko download dialog; mscoree says
# this when it has no Mono at all.
PROMPT_MARKERS = ("Got URL", "mono runtime not found")


def run_watched(cmd, env, log, timeout):
    """Runs a Wine command with its output added to log, and stops it at the first download prompt.
    Returns (the prompt's marker or None, the exit code or None if it did not finish in time, its output)."""
    mark = os.path.getsize(log) if os.path.exists(log) else 0
    with open(log, "a") as f:
        proc = subprocess.Popen(cmd, env=env, stdout=f, stderr=subprocess.STDOUT)
    deadline = time.time() + timeout
    while True:
        with open(log, errors="replace") as f:
            f.seek(mark)
            text = f.read()
        prompt = next((m for m in PROMPT_MARKERS if m in text), None)
        if prompt or proc.poll() is not None or time.time() > deadline:
            break
        time.sleep(1)
    code = proc.poll()
    if code is None:
        proc.kill()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass  # end_prefix ends it with the rest of the prefix
    return prompt, code, text


def winelibs_inputs(ctx):
    """The winelibs probe for each Windows half, and the engine files Wine's own code must load when
    it runs: every library Wine opens by file name (config.h's SONAME_* values, less the ones the
    engine does not carry) and the Unix modules that link GStreamer and FFmpeg."""
    probes = [compile_pe_tool(ctx["work"], "winelibs", bits, ["bcrypt", "secur32", "gdi32", "user32"])
              for bits in ("64", "32")]
    config = open(os.path.join(ctx["work"], "wine-install", ".build", "config.h")).read()
    names = sorted({v for k, v in re.findall(r'^#define (SONAME_\w+) "([^"]+)"$', config, re.M) if k not in NOT_CARRIED})
    # What a carried library opens at run time must load from the engine too (sdl2-compat's SDL3).
    opened = [carried for n in names for _, carried in OPENED_BY.get(n, [])]
    return probes, (["lib/" + n for n in names + opened]
                    + [f"lib/wine/x86_64-unix/{m}.so" for m in ("winegstreamer", "winedmo")])


def wineboot_check(engine, gecko_version, timeout=900, probes=(), required=()):
    """wineboot --init in a fresh prefix must finish with no download prompt and find the engine's
    Mono; then Wine Gecko must load from the engine in both halves (regsvr32 /i mshtml.dll makes
    mshtml load it, as a game's first web view would); then every check of each probe
    (winelibs_inputs) must pass. dyld lists the libraries every Wine process loads: none may come from
    outside the engine and macOS, and once the probes have run, each of `required` (paths in the
    engine) must be among them. Nothing here draws, so the Mac display driver is off throughout.
    Returns (problems, detail, log tail). Ends everything the prefix started (end_prefix) and removes
    the prefix, whatever happens."""
    home = tempfile.mkdtemp(prefix="wineboot-")
    env = dict(wine_env(engine, home), DYLD_PRINT_LIBRARIES="1")
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "wineboot.log")
    problems, start, loaded, probed, images = [], time.time(), [], [], []
    try:
        prompt, code, text = run_watched([wine, "wineboot", "--init"], env, log, timeout)
        if prompt:
            problems.append(f"a Mono or Gecko install prompt started (log: '{prompt}')")
        elif code is None:
            problems.append(f"wineboot --init did not finish in {timeout} s")
        else:
            problems += settle(engine, env, "wineboot --init")
            if code != 0:
                problems.append(f"wineboot --init exited {code}")
            if "mono runtime is at" not in text:
                problems.append("the log does not show Wine finding its Mono runtime")
            if not os.path.isfile(os.path.join(env["WINEPREFIX"], "system.reg")):
                problems.append("no system.reg in the new prefix")
        genv = dict(env, WINEDEBUG="fixme-all,+mshtml,+appwizcpl")
        for arch, regsvr32 in (("x86_64", "regsvr32"), ("x86", "C:\\windows\\syswow64\\regsvr32.exe")):
            if problems:
                break
            prompt, code, text = run_watched([wine, regsvr32, "/s", "/n", "/i", "mshtml.dll"], genv, log, 300)
            want = f"wine-gecko-{gecko_version}-{arch}"
            from_engine = [l for l in text.splitlines() if "load_xul" in l and want in l
                           and os.path.basename(engine) in l]
            if prompt:
                problems.append(f"loading Wine Gecko ({arch}) started a download prompt (log: '{prompt}')")
            elif code is None:
                problems.append(f"loading Wine Gecko ({arch}) did not finish in 300 s")
            elif not from_engine:
                problems.append(f"Wine did not load {want} from the engine (regsvr32 exited {code})")
            else:
                loaded.append(arch)
        ran = 0
        if not problems:
            p, probed, ran = run_probes(wine, [(probe, []) for probe in probes], env, log)
            problems += p
        # End every process the prefix started, then read what dyld printed for each of them.
        problems += end_prefix(engine, env)
        images = dyld_images(open(log, errors="replace").read())
        if not images:
            problems.append("dyld listed no libraries: the trace this gate reads is missing")
        problems += [f"a Wine process loaded {img}, outside the engine and macOS" for img in outside(images, engine)]
        if probes and ran == len(probes):
            seen = {os.path.realpath(i) for i in images}
            problems += [f"Wine's own code did not load {r} from the engine" for r in required
                         if os.path.realpath(os.path.join(engine, r)) not in seen]
    finally:
        problems += end_prefix(engine, env)
        lines = open(log, errors="replace").read().splitlines() if os.path.exists(log) else []
        tail = [l for l in lines if not l.startswith("dyld[")][-15:]
        if os.path.exists(log):
            shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-wineboot-last.log"))
        shutil.rmtree(home, ignore_errors=True)
    detail = "wineboot --init in a fresh prefix finds the engine's Mono"
    if loaded:
        detail += f"; Wine Gecko {gecko_version} loads from the engine ({', '.join(loaded)})"
    if probes and len(probed) == len(probes) and not problems:
        detail += (f"; Wine's own code opens {len(required)} libraries and modules from the engine "
                   f"({', '.join(os.path.basename(r) for r in required)}); all {len(set(images))} libraries "
                   f"its processes loaded are the engine's or macOS's; probes passed ({'; '.join(probed)})")
    return problems, f"{detail}; {time.time() - start:.0f} s", tail


def run_probes(wine, probes, env, log, timeout=300, forbid=(), require=()):
    """Runs each (Windows program, arguments) with Wine. Returns (problems, the probes whose every check
    passed, how many ran to the end): every "check" line must say ok, each must print "done", no line
    of its output may hold a text in forbid, and some line must hold each text in require."""
    problems, probed, ran = [], [], 0
    for probe, args in probes:
        name = os.path.basename(probe)
        prompt, code, text = run_watched([wine, probe] + list(args), dict(env, WINEDEBUG="fixme-all"), log, timeout)
        lines = text.splitlines()
        problems += [f"{name}: {l.strip()}" for l in lines if any(f in l for f in forbid)]
        problems += [f"{name}: no output line says \"{r}\"" for r in require if not any(r in l for l in lines)]
        checks = [l.split("\t") for l in lines if l.startswith("check\t")]
        problems += [f"{name}: {c[1]} failed ({c[3] if len(c) > 3 else '?'})" for c in checks if c[2:3] != ["ok"]]
        if any(l.startswith("done\t") for l in lines) and checks:
            ran += 1
            if all(c[2:3] == ["ok"] for c in checks):
                probed.append(f"{name}: " + "; ".join(f"{c[1]} {c[3] if len(c) > 3 else ''}".strip() for c in checks))
        else:
            problems.append(f"{name} did not run to the end (exit {code}{', timed out' if code is None else ''})")
    return problems, probed, ran


def no_crash_dialog(wine, env, log):
    """A probe that crashes must end, not wait behind Wine's crash dialog (Play's ShowCrashDialog=0)."""
    run_watched([wine, "reg", "add", "HKCU\\Software\\Wine\\WineDbg", "/v", "ShowCrashDialog",
                 "/t", "REG_DWORD", "/d", "0", "/f"], env, log, 120)


def probe_check(engine, probes, required=(), timeout=900, extra_env=None, draws=False, forbid=(), require=()):
    """A fresh prefix (wineboot --init), then each (Windows program, arguments) of probes, with
    extra_env added to Wine's environment. The Mac display driver is off, but for the probes
    themselves when draws is True. A probe's output line holding a text in forbid is a problem, and so is
    a text in require that no output line holds. dyld lists
    what every Wine process loads: nothing may come from outside the engine and macOS, and once every
    probe ran to the end, each of `required` (paths in the engine) must be among the loaded images.
    Returns (problems, the probes' results, the engine's loaded images). Ends everything the prefix
    started (end_prefix) and removes it, whatever happens."""
    home = tempfile.mkdtemp(prefix="probe-")
    env = dict(wine_env(engine, home), DYLD_PRINT_LIBRARIES="1", **(extra_env or {}))
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "probe.log")
    problems, probed, images = [], [], []
    try:
        prompt, code, _ = run_watched([wine, "wineboot", "--init"], env, log, timeout)
        if prompt or code != 0:
            problems.append(f"wineboot --init: {prompt or 'exit %s' % code}")
        else:
            no_crash_dialog(wine, env, log)
            problems += settle(engine, env, "wineboot --init")
            if not problems:
                p, probed, ran = run_probes(wine, probes, with_display(env) if draws else env, log, forbid=forbid,
                                            require=require)
                problems += p
        problems += end_prefix(engine, env)
        images = dyld_images(open(log, errors="replace").read())
        if not images:
            problems.append("dyld listed no libraries: the trace this gate reads is missing")
        problems += [f"a Wine process loaded {img}, outside the engine and macOS" for img in outside(images, engine)]
        if not problems:
            seen = {os.path.realpath(i) for i in images}
            problems += [f"Wine did not load {r} from the engine" for r in required
                         if os.path.realpath(os.path.join(engine, r)) not in seen]
    finally:
        problems += end_prefix(engine, env)
        if os.path.exists(log):
            shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-probe-last.log"))
        shutil.rmtree(home, ignore_errors=True)
    root = os.path.realpath(engine) + "/"
    loaded = sorted({os.path.relpath(os.path.realpath(i), root) for i in images if os.path.realpath(i).startswith(root)})
    return problems, probed, loaded


def wine_inf_fonts(engine):
    """{Windows name: source file name} from the engine's wine.inf FontFiles section."""
    inf = open(os.path.join(engine, "share", "wine", "wine.inf"), encoding="utf-8", errors="replace").read()
    m = re.search(r"^\[FontFiles\]\r?\n(.*?)(?=^\[)", inf, re.M | re.S)
    if not m:
        return {}
    fonts = {}
    for line in m.group(1).splitlines():
        line = line.split(";", 1)[0].strip()
        if line:
            fields = [f.strip() for f in line.split(",")]
            fonts[fields[0]] = fields[1] if len(fields) > 1 and fields[1] else fields[0]
    return fonts


def fonts_check(engine, timeout=900):
    """wineboot --init in a fresh prefix must copy every FontFiles entry of wine.inf into
    drive_c/windows/Fonts with its source's exact bytes (share/wine/fonts); then a file put in place
    of one of them must stay as it is through wineboot --update. The Mac display driver is off, so
    setupapi's prompt for a missing file can reach no screen (the bounded wait ends it). Returns
    (problems, detail). Ends everything the prefix started (end_prefix) and removes it, whatever
    happens."""
    fonts = wine_inf_fonts(engine)
    if not fonts:
        return ["wine.inf has no FontFiles section"], ""
    home = tempfile.mkdtemp(prefix="fonts-")
    env = wine_env(engine, home)
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "fonts.log")
    folder = os.path.join(env["WINEPREFIX"], "drive_c", "windows", "Fonts")

    def boot(step):  # Wine's processes must all end; a setup step left waiting (for a window's answer) fails
        prompt, code, _ = run_watched([wine, "wineboot", step], env, log, timeout)
        problems = settle(engine, env, f"wineboot {step}")
        return problems + ([f"wineboot {step}: {prompt or 'exit %s' % code}"] if prompt or code != 0 else [])

    def check():
        problems = boot("--init")
        if problems:
            return problems, ""
        for name, source in sorted(fonts.items()):
            src = os.path.join(engine, "share", "wine", "fonts", source)
            dst = os.path.join(folder, name)
            if not os.path.isfile(src):
                problems.append(f"{name}: its source share/wine/fonts/{source} is not in the engine")
            elif not os.path.isfile(dst):
                problems.append(f"{name} is not in C:\\windows\\Fonts after wineboot --init")
            elif open(src, "rb").read() != open(dst, "rb").read():
                problems.append(f"{name} in C:\\windows\\Fonts differs from share/wine/fonts/{source}")
        if problems:
            return problems, ""
        kept = sorted(fonts)[0]
        marker = b"mavrik gate: a font a game or the player put here\n"
        open(os.path.join(folder, kept), "wb").write(marker)
        problems = boot("--update")
        if problems:
            return problems, ""
        if open(os.path.join(folder, kept), "rb").read() != marker:
            problems.append(f"wineboot --update replaced the {kept} that was already in C:\\windows\\Fonts")
        return problems, (f"{len(fonts)} fonts copied into C:\\windows\\Fonts byte for byte ({', '.join(sorted(fonts))}); "
                          f"a file put in place of {kept} kept through wineboot --update")

    problems, detail = [], ""
    try:
        problems, detail = check()
    finally:
        problems = problems + end_prefix(engine, env)
        shutil.rmtree(home, ignore_errors=True)
    return problems, detail if not problems else ""


def gate_fonts(engine, ctx):
    problems, detail = fonts_check(engine)
    return not problems, detail, problems


def version_check(engine, expected):
    home = tempfile.mkdtemp(prefix="wineversion-")
    try:
        r = out([os.path.join(engine, "bin", "wine"), "--version"], env=wine_env(engine, home), timeout=120)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    got = r.stdout.strip()
    if got != expected:
        return [f"wine --version printed '{got}' (exit {r.returncode}), expected '{expected}'"], got
    return [], got


def gate_wine(engine, ctx):
    problems, got = version_check(engine, ctx["expected_version"])
    probes, required = winelibs_inputs(ctx)
    boot, detail, tail = wineboot_check(engine, ctx["inputs"]["inputs"]["wine-gecko-x86"]["version"],
                                        probes=probes, required=required)
    problems += boot
    if boot:
        problems += ["log: " + l for l in tail]
    return not problems, f"wine --version: {got}; {detail}", problems


def media_static(engine, files):
    """Every load path and run path of the media files: never the system framework, and every
    @rpath library found inside the engine through the file's own run paths."""
    problems = []
    for path in files:
        rel = os.path.relpath(path, engine)
        entries = macho_paths(path)
        rpaths = []
        for kind, value in entries:
            if "GStreamer.framework" in value or value.startswith("/Library/Frameworks"):
                problems.append(f"{rel}: {kind} {value}")
            if kind == "LC_RPATH" and value.startswith("@loader_path"):
                rpaths.append(os.path.normpath(value.replace("@loader_path", os.path.dirname(path))))
        for kind, value in entries:
            if kind.startswith("LC_LOAD") and value.startswith("@rpath/"):
                name = value[len("@rpath/"):]
                hits = [r for r in rpaths if os.path.exists(os.path.join(r, name))]
                if not hits:
                    problems.append(f"{rel}: {value} is not found through its run paths {rpaths}")
                elif not os.path.realpath(os.path.join(hits[0], name)).startswith(os.path.realpath(engine) + "/"):
                    problems.append(f"{rel}: {value} resolves outside the engine")
    return problems


def media_files(engine):
    unix = os.path.join(engine, "lib", "wine", "x86_64-unix")
    files = [os.path.join(unix, n) for n in ("winegstreamer.so", "winedmo.so")]
    lib = os.path.join(engine, "lib")
    files += [p for p in walk(lib) if p.endswith(".dylib") and not os.path.islink(p)
              and (os.path.basename(p).startswith(("libgst", "libav", "libsw", "libglib", "libgobject", "libgio",
                                                    "libgmodule", "libintl", "liborc"))
                   or "/gstreamer-1.0/" in p)]
    return files


def mediacheck(engine, work):
    exe = compile_tool(work, "mediacheck")
    home = tempfile.mkdtemp(prefix="mediacheck-")
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": home, "DYLD_PRINT_LIBRARIES": "1",
           "GST_REGISTRY_1_0": os.path.join(home, "registry.bin"), "GST_REGISTRY_FORK": "no",
           "XDG_DATA_HOME": os.path.join(home, "data"), "XDG_CACHE_HOME": os.path.join(home, "cache")}
    lib = os.path.join(engine, "lib")
    try:
        gst = out([exe, "gst", os.path.join(lib, "libgstreamer-1.0.0.dylib")] + GST_ELEMENTS, env=env, timeout=300)
        ff = out([exe, "ffmpeg", os.path.join(lib, "libavcodec.61.dylib")] + FFMPEG_DECODERS, env=env, timeout=120)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    os.makedirs(os.path.join(work, "gates"), exist_ok=True)
    open(os.path.join(work, "gates", "mediacheck-gst.txt"), "w").write(gst.stdout + "\n--- stderr ---\n" + gst.stderr)
    open(os.path.join(work, "gates", "mediacheck-ffmpeg.txt"), "w").write(ff.stdout)
    return exe, gst, ff


def gate_media(engine, ctx):
    problems = []
    present = os.path.exists(GST_FRAMEWORK)
    files = media_files(engine)
    missing = [f for f in files[:2] if not os.path.isfile(f)]
    problems += [f"missing {os.path.relpath(m, engine)}" for m in missing]
    problems += media_static(engine, [f for f in files if os.path.isfile(f)])
    exe, gst, ff = mediacheck(engine, ctx["work"])
    elements = [l.split("\t") for l in gst.stdout.splitlines() if l.startswith("element\t")]
    problems += [f"GStreamer element {e[2]} could not be created" for e in elements if e[1] != "ok"]
    if len(elements) != len(GST_ELEMENTS):
        problems.append(f"mediacheck gst exited {gst.returncode}: {gst.stdout[-500:]} {gst.stderr[-1500:]}")
    plugins = [l.split("\t") for l in gst.stdout.splitlines() if l.startswith("plugin\t")]
    plugdir = os.path.realpath(os.path.join(engine, "lib", "gstreamer-1.0")) + "/"
    problems += [f"plugin {p[1]} loaded from {p[3]}" for p in plugins
                 if p[3] != "(built in)" and not os.path.realpath(p[3]).startswith(plugdir)]
    problems += [f"GStreamer loaded {img}" for img in outside(dyld_images(gst.stderr), engine, [exe])]
    decoders = [l.split("\t") for l in ff.stdout.splitlines() if l.startswith("decoder\t")]
    problems += [f"FFmpeg decoder {d[2]} missing" for d in decoders if d[1] != "ok"]
    if len(decoders) != len(FFMPEG_DECODERS):
        problems.append(f"mediacheck ffmpeg exited {ff.returncode}: {ff.stdout[-500:]} {ff.stderr[-500:]}")
    problems += [f"FFmpeg loaded {img}" for img in outside(dyld_images(ff.stderr), engine, [exe])]
    version = next((l.split("\t", 1)[1] for l in gst.stdout.splitlines() if l.startswith("version\t")), "?")
    return not problems, (f"{version}: {len(files)} media files resolve inside the engine, "
                          f"{sum(1 for e in elements if e[1] == 'ok')} elements, {len(plugins)} plugins, "
                          f"{sum(1 for d in decoders if d[1] == 'ok')} FFmpeg decoders; "
                          f"{GST_FRAMEWORK} {'present on this Mac, and nothing loaded from it' if present else 'absent'}"), problems


def read_tsv(path):
    rows = []
    for i, line in enumerate(open(path)):
        if i == 0 or not line.strip():
            continue
        rows.append(line.rstrip("\n").split("\t"))
    return rows


def licence_problems(engine):
    lic = os.path.join(engine, "licences")
    problems = []
    try:
        files = read_tsv(os.path.join(lic, "FILES.tsv"))
        comps = {r[0]: r for r in read_tsv(os.path.join(lic, "COMPONENTS.tsv"))}
    except OSError as e:
        return [f"licence list missing: {e}"], 0
    exact = {r[0]: r[1] for r in files if "*" not in r[0]}
    patterns = [(r[0], r[1]) for r in files if "*" in r[0]]
    used = set()
    count = 0
    for path in walk(engine):
        rel = os.path.relpath(path, engine)
        count += 1
        comp = exact.get(rel)
        if comp is None:
            comp = next((c for p, c in patterns if fnmatch.fnmatchcase(rel, p)), None)
            if comp is not None:
                used.add(next(p for p, c in patterns if fnmatch.fnmatchcase(rel, p)))
        if comp is None:
            problems.append(f"not covered by licences/FILES.tsv: {rel}")
        elif comp not in comps:
            problems.append(f"{rel}: component {comp} has no line in COMPONENTS.tsv")
    for rel in exact:
        if not os.path.lexists(os.path.join(engine, rel)):
            problems.append(f"FILES.tsv names {rel}, which is not in the engine")
    for p, _ in patterns:
        if p not in used:
            problems.append(f"FILES.tsv pattern {p} matches nothing")
    for name, row in comps.items():
        notices = [n for n in row[4].split(",") if n] if len(row) > 4 else []
        if not notices:
            problems.append(f"component {name} has no licence text")
        for n in notices:
            p = os.path.join(lic, n)
            if not os.path.isfile(p) or os.path.getsize(p) == 0:
                problems.append(f"component {name}: notice {n} missing or empty")
    return problems, count


def gate_licences(engine, ctx):
    problems, count = licence_problems(engine)
    return not problems, f"{count} files, all covered; every component has its licence texts", problems


def nogpl_problems(engine, gst_out, ff_out):
    problems = []
    lic = os.path.join(engine, "licences")
    comps = {r[0]: r for r in read_tsv(os.path.join(lic, "COMPONENTS.tsv"))}
    media = [r for r in read_tsv(os.path.join(lic, "FILES.tsv")) if r[1].startswith("media:")]
    for path, comp in media:
        licence = comps.get(comp, [comp, "", "?"])[2]
        terms = re.findall(r"[A-Za-z0-9.+-]+", licence)
        if any(t.startswith("GPL") for t in terms) and not any(t.startswith("LGPL") for t in terms):
            problems.append(f"{path}: {licence}")
    for path in walk(os.path.join(engine, "lib")):
        base = os.path.basename(path).lower()
        if any(n in base for n in GPL_NAMES):
            problems.append(f"GPL or encumbered library present: {os.path.relpath(path, engine)}")
    for line in gst_out.splitlines():
        if line.startswith("plugin\t"):
            _, name, licence, _ = line.split("\t", 3)
            if licence not in ("LGPL", "unknown") or (licence == "unknown" and name != "mpegpsdemux"):
                problems.append(f"plugin {name} declares licence {licence}")
    lic_line = next((l for l in ff_out.splitlines() if l.startswith("license\t")), "")
    conf = next((l for l in ff_out.splitlines() if l.startswith("configuration\t")), "")
    if "LGPL" not in lic_line:
        problems.append(f"FFmpeg says {lic_line or 'nothing'}")
    for flag in ("--enable-gpl", "--enable-nonfree", "--enable-version3",
                 "-Dgpl=enabled", "-Dnonfree=enabled", "-Dversion3=enabled"):
        if flag in conf:
            problems.append(f"FFmpeg was configured with {flag}")
    return problems, len(media)


def gate_nogpl(engine, ctx):
    gates = os.path.join(ctx["work"], "gates")
    gst = open(os.path.join(gates, "mediacheck-gst.txt")).read().split("\n--- stderr ---\n")[0]
    ff = open(os.path.join(gates, "mediacheck-ffmpeg.txt")).read()
    problems, n = nogpl_problems(engine, gst, ff)
    return not problems, f"{n} media files: LGPL, BSD, MIT, Zlib or bzip2 only; FFmpeg is LGPL", problems


# ---------------------------------------------------------------- identity

ENGINE_IDENTIFIER = "org.mavrik.engine"
LOADER = "lib/wine/x86_64-unix/wine"
# CrossOver and CodeWeavers, in any case, as ASCII, UTF-16LE (Windows resources) and UTF-16BE (font tables).
_NAMES = (b"crossover", b"codeweavers")
_ENCODINGS = (("ascii", 1, 0), ("utf-16-le", 2, 0), ("utf-16-be", 2, 1))
# The names that stay, each with why no player sees it: (path pattern, the whole text, reason).
# A text is kept only when one pattern matches all of it, so a kept comment cannot hide a name beside it.
IDENTITY_ALLOWED = [
    ("*", r"[\s*(]*(Copyright[\s\d,-]+(\(C\)\s*)?)?[A-Z][\w.'-]*( [A-Z][\w.'-]*)* for CodeWeavers[).\s\d]*",
     "copyright and authorship lines of Wine's own code and data"),
    ("*", r"[\w .'-]*<[\w.+-]+@codeweavers\.com>", "an author's address in a GStreamer element winegstreamer registers"),
    ("*", r"(?i)[;\s]*crossover hack(, bug \d+|: [\w %,.:-]+)", "CrossOver's log lines and comments"),
    ("*", r"(?i)(trying |no|[._$a-z]*)?crossoverfallbac(k)?( return(ed|ing) %\w+|=%s|, verb=%s)?",
     "shell32's internal fallback: its function, trace and registry value names"),
    ("lib/wine/x86_64-unix/ntdll.so", r"\\Registry\\User\\[\w-]+\\Software\\CrossOver\\(SuppressAltLoader|UseAltLoader)",
     "registry keys ntdll reads only for CrossOver's alternative loader (CX_ALT_LOADER_SOCKET)"),
    ("share/wine/fonts/*", r"http://www\.codeweavers\.com",
     "the vendor address in the name table of Wine's own symbol font, as upstream Wine ships it"),
]


def _name_pattern(name, step, pad):
    parts = []
    for c in name:
        cls = b"[" + bytes([c]) + bytes([c]).upper() + b"]"
        parts.append((b"\x00" + cls) if (step == 2 and pad == 1) else (cls + b"\x00") if step == 2 else cls)
    return re.compile(b"".join(parts))


_NAME_PATTERNS = [(enc, step, pad, _name_pattern(n, step, pad)) for n in _NAMES for enc, step, pad in _ENCODINGS]


def _printable(data, i, step, pad):
    """True if the character at byte i (of width step, its value at offset pad) is printable text."""
    if i < 0 or i + step > len(data):
        return False
    ch = data[i + pad]
    other = data[i + 1 - pad] if step == 2 else 0
    return other == 0 and (32 <= ch < 127 or ch == 9)


def identity_texts(data):
    """Every printable string in data that names CrossOver or CodeWeavers, in each encoding."""
    found = set()
    for enc, step, pad, pattern in _NAME_PATTERNS:
        for m in pattern.finditer(data):
            start, end = m.start(), m.end()
            while _printable(data, start - step, step, pad):
                start -= step
            while _printable(data, end, step, pad):
                end += step
            found.add(data[start:end].decode(enc, "replace").strip())
    return found


def allowed_identity(rel, text):
    for path_pattern, text_pattern, _ in IDENTITY_ALLOWED:
        if fnmatch.fnmatchcase(rel, path_pattern) and re.fullmatch(text_pattern, text):
            return True
    return False


def loader_plist(path):
    """The Info.plist built into the loader (its __TEXT,__info_plist section), as a dict."""
    data = open(path, "rb").read()
    start = data.find(b"<?xml")
    end = data.find(b"</plist>", start)
    if start < 0 or end < 0:
        return None
    return plistlib.loads(data[start:end + len(b"</plist>")])


def identity_problems(engine, files):
    """files: paths in the engine to scan (Wine's own files: they come from the CrossOver tree)."""
    problems, kept = [], {}
    loader = os.path.join(engine, LOADER)
    info = loader_plist(loader) if os.path.isfile(loader) else None
    if info is None:
        problems.append(f"{LOADER}: no Info.plist")
    else:
        if info.get("CFBundleIdentifier") != ENGINE_IDENTIFIER:
            problems.append(f"{LOADER}: CFBundleIdentifier is {info.get('CFBundleIdentifier')!r}, not {ENGINE_IDENTIFIER}")
        for key in ("CFBundleName", "CFBundleExecutable"):
            if re.search(r"(?i)crossover|codeweavers", str(info.get(key, ""))):
                problems.append(f"{LOADER}: {key} is {info.get(key)!r}")
    for rel in files:
        path = os.path.join(engine, rel)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        for text in sorted(identity_texts(open(path, "rb").read())):
            if allowed_identity(rel, text):
                kept[text] = kept.get(text, 0) + 1
            else:
                problems.append(f"{rel}: {text[:160]!r}")
    return problems, kept


def wine_files(engine):
    return [r[0] for r in read_tsv(os.path.join(engine, "licences", "FILES.tsv")) if r[1] == "wine" and "*" not in r[0]]


def gate_identity(engine, ctx):
    files = wine_files(engine)
    problems, kept = identity_problems(engine, files)
    info = loader_plist(os.path.join(engine, LOADER)) or {}
    return not problems, (f"the loader is {info.get('CFBundleIdentifier')} ({info.get('CFBundleName')}); "
                          f"{len(files)} Wine files scanned, {len(kept)} reviewed internal names kept, none a player sees"), problems


# ---------------------------------------------------------------- build paths

def build_paths(ctx):
    """The folders a build machine's paths would come from: the work folder and the recipe."""
    return sorted({p for d in (ctx["work"], REPO) for p in (d, os.path.realpath(d))})


def buildpath_problems(engine, needles):
    pats = [(n, n.encode(enc)) for n in needles for enc in ("utf-8", "utf-16-le")]
    problems, count = [], 0
    for path in walk(engine):
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        count += 1
        data = open(path, "rb").read()
        hits = sorted({n for n, b in pats if b in data})
        if hits:
            problems.append(f"{os.path.relpath(path, engine)} contains {', '.join(hits)}")
    return problems, count


def gate_buildpaths(engine, ctx):
    needles = build_paths(ctx)
    problems, count = buildpath_problems(engine, needles)
    return not problems, f"{count} files, none names {' or '.join(needles)}", problems


# ---------------------------------------------------------------- d3d11 and playback

def metal_device(work):
    """The name of this machine's default Metal device, or None (as an x86_64 program, as DXMT sees it)."""
    exe = compile_tool(work, "metaldevice", ("Metal", "Foundation"))
    r = out([exe], timeout=60)
    name = r.stdout.strip()
    return name if r.returncode == 0 and name else None


# What DXMT logs when a frame waited for under vsync is not presented within 100 ms (dxmt/patches/0002).
PRESENT_TIMEOUT = "not presented within"
# A line DXMT's log always prints when a device is made (src/d3d11/d3d11.cpp): it shows DXMT's log reaches the
# probe's output, so the absence of PRESENT_TIMEOUT means something.
DXMT_LOG_LINE = "Using feature level"
# Said beside a presentation timeout: a display that sleeps (or a locked screen) presents no frame either.
PRESENT_TIMEOUT_HINT = ("; a sleeping display or a locked screen presents no frames too, so check the screen was "
                        "awake before reading this as a broken engine")


def d3d11_check(engine, ctx):
    probe = compile_pe_tool(ctx["work"], "d3d11probe", "64", ["d3d11", "dxgi", "uuid", "gdi32", "user32"])
    required = ["lib/wine/x86_64-unix/winemetal.so", "lib/wine/x86_64-unix/winemac.so"]
    problems, probed, loaded = probe_check(engine, [(probe, [])], required, draws=True, forbid=[PRESENT_TIMEOUT],
                                           require=[DXMT_LOG_LINE])
    problems = [p + PRESENT_TIMEOUT_HINT if PRESENT_TIMEOUT in p else p for p in problems]
    return problems, probed


def gate_d3d11(engine, ctx):
    device = metal_device(ctx["work"])
    if not device:
        return None, "SKIP: this machine has no Metal device, so DXMT cannot run here", []
    problems, probed = d3d11_check(engine, ctx)
    return not problems, f"Metal device {device}; " + "; ".join(probed) + "; DXMT's winemetal.so and winemac.so loaded from the engine", problems


SAMPLE = os.path.join(REPO, "tools", "media", "sample.mp4")
# The plugins a decoded H.264 and AAC movie needs: the MP4 demuxer and FFmpeg's decoders.
PLAYBACK_PLUGINS = ["lib/gstreamer-1.0/libgstisomp4.dylib", "lib/gstreamer-1.0/libgstlibav.dylib"]


def playback_check(engine, ctx):
    probes = [compile_pe_tool(ctx["work"], "mediaprobe", bits, ["mfplat", "mfreadwrite", "mfuuid", "ole32", "uuid"],
                              extra=["-municode"]) for bits in ("64", "32")]
    sample = "Z:" + SAMPLE.replace("/", "\\")
    required = ["lib/wine/x86_64-unix/winegstreamer.so"] + PLAYBACK_PLUGINS
    problems, probed, loaded = probe_check(engine, [(p, [sample]) for p in probes], required)
    return problems, probed, loaded


def gate_playback(engine, ctx):
    problems, probed, loaded = playback_check(engine, ctx)
    plugins = [l for l in loaded if l.startswith("lib/gstreamer-1.0/")]
    return not problems, ("; ".join(probed) + f"; {len(plugins)} GStreamer plugins loaded from the engine "
                          f"({', '.join(os.path.basename(p) for p in plugins)}), nothing from outside it"), problems


# ---------------------------------------------------------------- steamredirect and dockname

def steamredirect_probes(work):
    """For each half, a folder holding steamprobeNN.exe and its two DLLs, all from tools/steamprobe.c:
    a stand-in for Valve's steamclient (steamclient64.dll or steamclient.dll) and for lsteamclient.dll."""
    src = os.path.join(REPO, "tools", "steamprobe.c")
    probes = []
    for bits, client in (("64", "steamclient64"), ("32", "steamclient")):
        folder = os.path.join(work, "tools", "steamredirect" + bits)
        os.makedirs(folder, exist_ok=True)
        for name, extra in ((client + ".dll", ["-DPROBE_DLL=1", "-shared"]),
                            ("lsteamclient.dll", ["-DPROBE_DLL=2", "-shared"]), (f"steamprobe{bits}.exe", [])):
            path = os.path.join(folder, name)
            if stale(path, src):
                subprocess.run([PE_COMPILERS[bits], "-O1", "-s"] + extra + ["-o", path, src], check=True)
        probes.append(os.path.join(folder, f"steamprobe{bits}.exe"))
    return probes


def steamredirect_check(engine, ctx, extra_env=None):
    probes = [(p, []) for p in steamredirect_probes(ctx["work"])]
    problems, probed, loaded = probe_check(engine, probes, extra_env=extra_env)
    return problems, probed


def gate_steamredirect(engine, ctx):
    problems, probed = steamredirect_check(engine, ctx)
    return not problems, "; ".join(probed), problems


# The titles the dockname gate gives WINEPRELOADERAPPNAME, each within the loader's 32-byte name slot
# once escaped and within the window server's 31 bytes decomposed, so both must show it exactly (the
# window server in its decomposed form): a plain one; one with the characters XML escapes (a raw '&' or
# '<' makes Core Foundation reject the loader's whole Info.plist); and one with accented, CJK and emoji
# characters.
DOCK_NAMES = ["Gate Dock Name", "Gate & Dock <Name>", "Gâte Dock 名前 🎮"]
# Titles each source shows changed, as dock_cases says: a CJK title of 36 bytes, cut in both (to 30
# bytes for the Dock; to 27 for the window server, where its katakana "ゲ" takes 6 bytes decomposed); one with
# '/', which a file name cannot hold; and "Control", the name of one of Wine's own programs, which the
# loader started through a link of that name must not run instead of the game.
DOCK_CUT_NAMES = ["日本語のゲーム名前テスト", "AC/DC Gate", "Control"]
# The name of a program started with no link: the loader in mavrik.app (patch 0037) then names it after
# its bundle, in LaunchServices, the window server and the app menu alike ("mavrik"; never "wine").
# Written out, not read from the bundle, so a renamed bundle fails here.
BUNDLE_NAME = "mavrik"
# A title no link can be named after: the program starts from the loader in mavrik.app, so every name is
# the bundle's, for the 32-bit child too (it keeps the title, so it has no link either).
DOCK_FALLBACK = ("..", BUNDLE_NAME, BUNDLE_NAME)
# No title, and an argv[0] that is not UTF-8 (a lead byte and 40 continuation bytes), which the loader's
# first process would name its link after: the bounded cut must refuse it (no link: the bundle's name)
# and the program must start. Its 32-bit child keeps its own file's name, since no title is set and its
# link is named after its file.
DOCK_NO_TITLE = (None, {"dockprobe64.exe": BUNDLE_NAME, "dockprobe32.exe": "dockprobe32"},
                 {"dockprobe64.exe": BUNDLE_NAME, "dockprobe32.exe": "dockprobe32"}, b"\xc3" + b"\x80" * 40)


def slot_name(title, slot=32):
    """The name patch 0006 gives LaunchServices: as much of title as fits the loader's Info.plist name
    slot once '&', '<' and '>' are escaped, cut between whole characters and escapes."""
    name, used = "", 0
    for ch in title:
        cost = {"&": 5, "<": 4, ">": 4}.get(ch, len(ch.encode()))
        if used + cost > slot:
            break
        name, used = name + ch, used + cost
    return name


def link_name(title):
    """The name of the link patch 0007 starts a program through: control characters dropped, '/' as
    U+2215, cut between whole characters (a character with its combining marks) where the decomposed
    (NFD) UTF-8 form still fits in 31 bytes."""
    clusters = []
    for ch in title:
        if unicodedata.category(ch) == "Cc":
            continue
        ch = "\u2215" if ch == "/" else ch
        if clusters and unicodedata.combining(ch):
            clusters[-1] += ch
        else:
            clusters.append(ch)
    name, used = "", 0
    for c in clusters:
        size = len(unicodedata.normalize("NFD", c).encode())
        if used + size > 31:
            break
        name, used = name + c, used + size
    return name


def window_server_name(title):
    """What the window server shows for a program started through patch 0007's link: the link's name,
    decomposed (NFD), as macOS keeps it (S193 lab: 'Gâte' reads back with a combining accent)."""
    return unicodedata.normalize("NFD", link_name(title))


def dock_cases(exact=DOCK_NAMES, changed=DOCK_CUT_NAMES):
    """(title, LaunchServices' name, the window server's name) for each title."""
    return ([(t, t, window_server_name(t)) for t in exact] + [(t, slot_name(t), window_server_name(t)) for t in changed]
            + [DOCK_FALLBACK, DOCK_NO_TITLE])


def link_folder(engine, loader=LOADER_BUNDLE_EXE):
    """Where patch 0007 (CW HACK 22144's folder) keeps the links to one of this engine's loaders: the user's
    temp folder, winetemp-<inode>-<size>-<mtime seconds>-<mtime nanoseconds> of the loader. Wine starts
    programs from the one in mavrik.app (patch 0037); an ntdll without 0037 or an engine without the
    bundle uses LOADER. None if that loader is not there."""
    path = os.path.join(engine, loader)
    if not os.path.isfile(path):
        return None
    st = os.stat(path)
    tmp = out(["getconf", "DARWIN_USER_TEMP_DIR"]).stdout.strip().rstrip("/")
    return f"{tmp}/winetemp-{st.st_ino}-{st.st_size}-{st.st_mtime_ns // 10**9}-{st.st_mtime_ns % 10**9}"


def proc_names(work, pid):
    """(the window server's owner name of pid's windows, pid's executable path), "-" where none
    (tools/procnames.c)."""
    tool = compile_tool(work, "procnames", frameworks=("CoreGraphics", "CoreFoundation"))
    fields = out([tool, str(pid)], timeout=30, encoding="utf-8", errors="replace").stdout.rstrip("\n").split("\t")
    return (fields[1], fields[2]) if len(fields) == 3 else ("-", "-")


def ls_info(pid, key):
    """One item of LaunchServices' information on the process pid ("name" or "ApplicationType"), or None.
    lsappinfo prints it in one of two forms: "KEY"="VALUE" (macOS 26 and before), or, since macOS 27, the
    whole record, with the name as its first quoted string ("NAME" ASN:...) and the type as type="VALUE".
    Any \\uXXXX escapes in lsappinfo's output are read back as the characters they stand for."""
    r = out(["lsappinfo", "info", "-only", key, str(pid)], timeout=30, encoding="utf-8", errors="replace")
    text = r.stdout.strip()
    m = re.search(r'^"[^"]+"="(.*)"\s*$', text)
    if not m and key == "name":
        m = re.match(r'"(.*)" ASN:', text)
    elif not m and key == "ApplicationType":
        m = re.search(r'(?<![!\w])type="([^"]*)"', text)
    if not m:
        return None
    value = re.sub(r"\\[uU]([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), m.group(1))
    return value.encode("utf-16", "surrogatepass").decode("utf-16")


def pids_named(name):
    """The processes whose name is name, in any case (as Windows compares names). Wine names each process
    after its Windows program, by its Unix path or, for a program another one started, its Windows
    path."""
    # ps cuts a process name at a fixed number of bytes, which can split a character (the dockname gate's own
    # titles are not all ASCII), so undecodable bytes are replaced; the names looked for are program file names.
    r = subprocess.run(["/bin/ps", "-axo", "pid=,comm="], capture_output=True)
    found = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and re.split(r"[/\\]", parts[1].strip())[-1].lower() == name.lower():
            found.append(int(parts[0]))
    return found


def dock_names_once(wine, probes, env, log, case, timeout, root, work):
    """dockprobe64.exe with WINEPRELOADERAPPNAME=title: it shows a window and starts dockprobe32.exe (a
    32-bit child, as a game's launcher starts the game), which shows its own. case is (title, the
    LaunchServices name, the window server's name). Once each is a Dock app, its LaunchServices name
    (what the Dock and the app switcher show) and the window server's owner name of its windows (what
    the menu bar and Cmd-Tab show) must be the case's, and its executable must be the loader in root's
    mavrik.app (root is the engine, with a trailing slash). Wine's control panel must not start. Only processes that started after this run began
    count, so a probe left by another run is never read.
    Returns (problems, {program: (LaunchServices' name, the window server's name)})."""
    title, want_ls, want_ws = case[:3]
    argv0 = case[3] if len(case) > 3 else None
    programs = [os.path.basename(p) for p in (probes["64"], probes["32"])]
    before = {program: set(pids_named(program)) for program in programs + ["control.exe"]}
    child = "Z:" + probes["32"].replace("/", "\\")
    run_env = dict(env, WINEDEBUG="fixme-all")
    if title is not None:
        run_env["WINEPRELOADERAPPNAME"] = title
    with open(log, "a") as f:
        proc = subprocess.Popen([argv0 or wine, probes["64"], child], executable=wine, stdout=f,
                                stderr=subprocess.STDOUT, env=run_env)
    problems, names, paths = [], {}, {}
    deadline = time.time() + timeout
    while time.time() < deadline and len(names) < len(programs):
        for program in programs:
            new = [pid for pid in pids_named(program) if pid not in before[program]]
            if len(new) > 1:
                problems.append(f"{program}: {len(new)} new processes ({new}); cannot tell which is the probe")
                return problems, names
            if new and program not in names and ls_info(new[0], "ApplicationType") == "Foreground":
                time.sleep(1)  # the name is set before the process turns into a Dock app
                owner, paths[program] = proc_names(work, new[0])
                while owner == "-" and time.time() < deadline:  # a window not yet listed
                    time.sleep(0.5)
                    owner, paths[program] = proc_names(work, new[0])
                names[program] = (ls_info(new[0], "name"), owner)
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    control = [pid for pid in pids_named("control.exe") if pid not in before["control.exe"]]
    if control:
        problems.append(f"Wine's control panel started (control.exe, {control}), not the program")
    for program in programs:
        if program not in names:
            problems.append(f"{program} never became a Dock app (a window) in {timeout} s")
            continue
        ls, ws = names[program]
        ls_wanted = want_ls[program] if isinstance(want_ls, dict) else want_ls
        ws_wanted = want_ws[program] if isinstance(want_ws, dict) else want_ws
        if ls != ls_wanted:
            problems.append(f"{program}: the Dock shows '{ls}', not '{ls_wanted}'")
        if ws != ws_wanted:
            problems.append(f"{program}: the window server shows '{ws}', not '{ws_wanted}'")
        # The raw path, as mavrik's Stop and engine checks read it (no realpath on the process side).
        if not paths[program].startswith(root):
            problems.append(f"{program}: started from {paths[program]}, outside the engine")
        elif paths[program] != root + LOADER_BUNDLE_EXE:
            problems.append(f"{program}: started from {paths[program]}, not from the loader in {LOADER_BUNDLE}")
    return problems, names


def dockname_check(engine, ctx, cases=None, timeout=60, extra_env=None):
    """A fresh prefix, then for each case of cases (dock_cases(); a plain title means that title in
    both sources) the two probes (dock_names_once), with everything the prefix started ended between
    cases, and extra_env added to Wine's environment. Returns (problems, {title: the names seen}). Kills
    everything the prefix started, removes it, and removes the links patch 0007 made to this engine's
    loader."""
    cases = [(c, c, c) if isinstance(c, str) else c for c in (cases or dock_cases())]
    probes = {bits: compile_pe_tool(ctx["work"], "dockprobe", bits, ["user32"]) for bits in ("64", "32")}
    home = tempfile.mkdtemp(prefix="dock-")
    env = dict(wine_env(engine, home), **(extra_env or {}))
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "dock.log")
    root = os.path.realpath(engine).rstrip("/") + "/"
    problems, seen = [], {}
    try:
        prompt, code, _ = run_watched([wine, "wineboot", "--init"], env, log, 900)
        if prompt or code != 0:
            problems.append(f"wineboot --init: {prompt or 'exit %s' % code}")
            return problems, seen
        no_crash_dialog(wine, env, log)
        problems += settle(engine, env, "wineboot --init")
        for case in cases if not problems else []:
            label = case[0] if case[0] is not None else "(no title, argv[0] not UTF-8)"
            # The probes' windows are what this gate reads, so they run with the Mac display driver.
            found, seen[label] = dock_names_once(wine, probes, with_display(env), log, case, timeout, root, ctx["work"])
            problems += [f"'{label}': {p}" for p in found]
            problems += [f"'{label}': {p}" for p in end_prefix(engine, env)]
    finally:
        problems += end_prefix(engine, env)
        if os.path.exists(log):
            shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-dock-last.log"))
        shutil.rmtree(home, ignore_errors=True)
        for loader in (LOADER_BUNDLE_EXE, LOADER):  # their links are programs Wine just ran (remove_deferred)
            if link_folder(engine, loader):
                remove_later(link_folder(engine, loader))
    return problems, seen


def login_session():
    """The launchd session this process runs in ("Aqua" is a user's login session, where a window can
    become a Dock app; "Background" is, for one, an ssh login's), or "" if launchctl does not say."""
    return out(["launchctl", "managername"], timeout=30).stdout.strip()


def gate_dockname(engine, ctx):
    session = login_session()
    if session != "Aqua":
        return None, (f"SKIP: the gates run in launchd's '{session or 'unknown'}' session, not a login (Aqua) "
                      "session, so no window can become a Dock app"), []
    problems, seen = dockname_check(engine, ctx)
    names = "; ".join(f"'{t}': " + ", ".join(f"{p} '{ls}' / '{ws}'" for p, (ls, ws) in s.items())
                      for t, s in seen.items())
    return not problems, (f"the names (Dock / window server): {names}; every program's executable is the "
                          "loader in the engine's mavrik.app"), problems


# ---------------------------------------------------------------- the loader bundle (Game Mode)

def loader_bundle_problems(engine):
    """What is wrong with the engine's loader bundle (assemble.py step 8), or []."""
    bundle = os.path.join(engine, LOADER_BUNDLE)
    exe = os.path.join(engine, LOADER_BUNDLE_EXE)
    plist = os.path.join(bundle, "Contents", "Info.plist")
    if not os.path.isfile(exe) or not os.path.isfile(plist):
        return [f"{LOADER_BUNDLE}: no Contents/MacOS/wine or no Contents/Info.plist"]
    problems = []
    try:
        info = plistlib.load(open(plist, "rb"))
    except Exception as e:
        return [f"{LOADER_BUNDLE}: the Info.plist does not parse ({e})"]
    want = loader_bundle_plist(info.get("CFBundleVersion", ""))
    for key in sorted(set(want) | set(info)):
        if info.get(key) != want.get(key):
            problems.append(f"{LOADER_BUNDLE}: {key} is {info.get(key)!r}, not {want.get(key)!r}")
    if not os.access(exe, os.X_OK):
        problems.append(f"{LOADER_BUNDLE_EXE}: not executable")
    with tempfile.TemporaryDirectory(prefix="gamemode-") as tmp:
        bare = os.path.join(tmp, "wine")
        shutil.copyfile(exe, bare)
        out(["codesign", "--remove-signature", bare], timeout=60)
        if open(bare, "rb").read() != open(os.path.join(engine, LOADER), "rb").read():
            problems.append(f"{LOADER_BUNDLE_EXE}: not the engine's loader ({LOADER}) with a signature added")
    r = out(["codesign", "--verify", "--strict", bundle], timeout=60)
    if r.returncode:
        problems.append(f"{LOADER_BUNDLE}: the signature does not verify: {((r.stderr or r.stdout).strip().splitlines() or [''])[0][-200:]}")
    return problems


def gate_gamemode(engine, ctx):
    problems = loader_bundle_problems(engine)
    return not problems, (f"{LOADER_BUNDLE}: the games category and Game Mode support, the engine's loader, "
                          "signed with its Info.plist sealed"), problems


# ---------------------------------------------------------------- controllers

PAD_LIBS = ["dinput8", "dxguid", "hid", "runtimeobject", "ole32"]
PAD_IDS = ["045e:028e", "054c:09cc", "054c:0ce6", "057e:2009"]
PAD_CHECKS = 18   # gamepadprobe's selftest
PAD_ABSENT_CHECKS = 2   # gamepadprobe's selftest absent


def pad_cases():
    """(name, bits, the Unix environment the session starts with, the probe's selftest arguments)."""
    cases = [(f"{vid} {bits}-bit", bits, {"MAVRIK_PAD_VIRTUAL": vid}, []) for bits in ("64", "32") for vid in PAD_IDS]
    cases += [(f"{vid} {bits}-bit with MAVRIK_PAD_HIDRAW=1", bits, {"MAVRIK_PAD_VIRTUAL": vid, "MAVRIK_PAD_HIDRAW": "1"},
               ["absent"]) for vid, bits in (("054c:09cc", "64"), ("054c:0ce6", "32"))]
    return cases


def stop_session(engine, env, step):
    """Ends the prefix's wineserver session (wineserver -k, then -w), then checks nothing of the prefix is left."""
    try:
        subprocess.run([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, capture_output=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        pass  # end_prefix reports it
    return settle(engine, env, step, bound=60) + end_prefix(engine, env)


def controllers_check(engine, ctx, cases=None, timeout=900):
    """A fresh prefix (wineboot --init, the display driver off), then each case of pad_cases() in its own wineserver
    session: tools/gamepadprobe.c's selftest must pass every check (PAD_CHECKS, or PAD_ABSENT_CHECKS for "absent"),
    and each check that failed is a problem. Ends everything the prefix started and removes it, whatever happens.
    Returns (problems, the cases that passed)."""
    probes = {bits: compile_pe_tool(ctx["work"], "gamepadprobe", bits, PAD_LIBS) for bits in ("64", "32")}
    home = tempfile.mkdtemp(prefix="pads-")
    env = dict(wine_env(engine, home), WINEDEBUG="fixme-all")
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "pads.log")
    problems, passed = [], []
    try:
        prompt, code, _ = run_watched([wine, "wineboot", "--init"], env, log, timeout)
        if prompt or code != 0:
            problems.append(f"wineboot --init: {prompt or 'exit %s' % code}")
        else:
            no_crash_dialog(wine, env, log)
            problems += stop_session(engine, env, "wineboot --init")
        for name, bits, extra, args in ([] if problems else cases or pad_cases()):
            case_env = dict(env, **extra)
            prompt, code, text = run_watched([wine, probes[bits], "selftest"] + args, case_env, log, 180)
            problems += [f"{name}: {p}" for p in stop_session(engine, case_env, name)]
            lines = text.splitlines()
            problems += [f"{name}: {l[5:].strip()}" for l in lines if l.startswith("FAIL ")]
            want = PAD_ABSENT_CHECKS if args else PAD_CHECKS
            total = [m for m in (re.match(r"gamepad selftest: (\d+)/(\d+) passed", l) for l in lines) if m]
            if not total:
                problems.append(f"{name}: the probe did not run to the end (exit {code}{', timed out' if code is None else ''})")
            elif (int(total[-1][1]), int(total[-1][2])) != (want, want):
                problems.append(f"{name}: {total[-1][1]} of {total[-1][2]} checks passed, not {want} of {want}")
            else:
                passed.append(f"{name} {want}/{want}")
    finally:
        problems += end_prefix(engine, env)
        if os.path.exists(log):
            shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-pads-last.log"))
        shutil.rmtree(home, ignore_errors=True)
    return problems, passed


def gate_controllers(engine, ctx):
    problems, passed = controllers_check(engine, ctx)
    return not problems, "selftest " + "; ".join(passed), problems


GATES = [("relocatable", gate_relocatable), ("dlopen", gate_dlopen), ("pe32", gate_pe32),
         ("winemac", gate_winemac), ("addons", gate_addons), ("wine", gate_wine), ("fonts", gate_fonts),
         ("media", gate_media), ("licences", gate_licences), ("nogpl", gate_nogpl),
         ("identity", gate_identity), ("buildpaths", gate_buildpaths), ("dxmt", gate_dxmt), ("d3d11", gate_d3d11),
         ("playback", gate_playback), ("steamredirect", gate_steamredirect), ("dockname", gate_dockname),
         ("controllers", gate_controllers), ("gamemode", gate_gamemode)]


# ---------------------------------------------------------------- running

def context(work):
    work = os.path.abspath(work)
    inputs = json.load(open(open(os.path.join(work, "inputs.path")).read().strip()))
    paths = json.load(open(os.path.join(work, "downloads", "paths.json")))
    version = open(os.path.join(work, "wine-src", "VERSION")).read().strip()
    expected = "wine-" + version.replace("Wine version ", "")
    masks = [os.path.join(work, "deps"), os.path.join(work, "gstreamer"), os.path.join(work, "wine-install")]
    return {"work": work, "inputs": inputs, "paths": paths, "expected_version": expected, "mask": masks}


def report(results, title):
    lines = [f"### {title}", "", "| gate | result | detail |", "|---|---|---|"]
    for r in results:
        lines.append(f"| {r['gate']} | {r['result']} | {r['detail']} |")
    for r in results:
        if r["problems"]:
            lines += ["", f"**{r['gate']}**", "```"] + r["problems"][:40] + ["```"]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text)


def syspolicyd_stop(since):
    """(True, why) once a syspolicyd crash report was written since the time since."""
    crashes = syspolicyd_crashes(since)
    if not crashes:
        return False, ""
    when = time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(crashes[0])))
    return True, (f"not run: macOS's syspolicyd crashed at {when} ({len(crashes)} report(s) in {CRASH_REPORTS}) "
                  "while the gates ran; new programs wait while it is down, so no more were started")


def run_gates(engine, work):
    ctx = context(work)
    engine = os.path.abspath(engine)
    results, start = [], time.time()
    syspolicyd_watch()
    for name, fn in GATES:
        t = time.time()
        stop, why = syspolicyd_stop(start)
        if stop:
            ok, detail, problems = False, why, [why]
        else:
            try:
                ok, detail, problems = fn(engine, ctx)
            except Exception as e:  # a gate that cannot run is a failed gate
                ok, detail, problems = False, f"the gate itself failed: {e!r}", [repr(e)]
        result = "SKIP" if ok is None else "PASS" if ok else "FAIL"
        results.append({"gate": name, "result": result, "detail": detail,
                        "problems": problems, "seconds": round(time.time() - t, 1)})
        print(f"{name}: {result} ({time.time() - t:.0f} s) {detail}", flush=True)
        for p in problems[:30]:
            print("   " + p)
    os.makedirs(os.path.join(ctx["work"], "gates"), exist_ok=True)
    remove_deferred()
    json.dump(results, open(os.path.join(ctx["work"], "gates", "results.json"), "w"), indent=2)
    report(results, "Gates")
    return all(r["result"] in ("PASS", "SKIP") for r in results)


def main(argv):
    if len(argv) == 4 and argv[1] == "addons-source":
        problems, mono, gecko = addons_source_problems(argv[2], json.load(open(argv[3])))
        print(f"addons.c: Wine Mono {mono}, Wine Gecko {gecko}")
        if problems:
            for p in problems:
                print("::error::" + p)
            sys.exit(1)
        return
    if len(argv) == 4 and argv[1] == "run":
        sys.exit(0 if run_gates(argv[2], argv[3]) else 1)
    if len(argv) == 4 and argv[1] == "selftest":
        sys.path.insert(0, HERE)
        import selftest
        sys.exit(0 if selftest.run(argv[2], argv[3]) else 1)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
