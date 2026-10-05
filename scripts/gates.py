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
  wine          wine --version prints the expected version, and wineboot --init in a fresh
                prefix finishes with no Mono or Gecko download prompt
  media         GStreamer and FFmpeg load from inside the engine, never from
                /Library/Frameworks/GStreamer.framework, and build the elements Wine uses. A Mac
                that has the framework is not changed: every library dyld loads and every plugin
                file must still be inside the engine, which is the case that matters on a
                player's Mac with GStreamer installed
  licences      every file in the engine is covered by a line in licences/FILES.tsv, and every
                component has its licence texts
  nogpl         no GPL-only file in the media component
"""
import fnmatch
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

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


def compile_tool(work, name):
    exe = os.path.join(work, "tools", name)
    if not os.path.exists(exe):
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        subprocess.run(["clang", "-O1", "-arch", "x86_64", "-o", exe, os.path.join(REPO, "tools", name + ".c")], check=True)
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
        env = {"PATH": "/usr/bin:/bin", "HOME": tempfile.mkdtemp(), "DYLD_PRINT_LIBRARIES": "1",
               "DYLD_FALLBACK_LIBRARY_PATH": "/usr/lib"}
        r = out([exe] + libs, env=env)
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


def gate_winemac(engine, ctx):
    so = os.path.join(engine, "lib", "wine", "x86_64-unix", "winemac.so")
    cx = os.path.join(ctx["work"], "wine-src", "dlls", "winemac.drv", "d3dmetal.c")
    problems, notes = winemac_check(so, cx, ctx["paths"]["dxmt-winemetal-source"])
    return not problems, "; ".join(["_macdrv_functions exported, layout matches DXMT v0.80"] + notes) if not problems else "; ".join(notes), problems


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


def wine_env(engine, home):
    return {"PATH": f"{engine}/bin:/usr/bin:/bin", "HOME": home, "WINEPREFIX": os.path.join(home, "prefix"),
            "WINEDEBUG": "fixme-all,+mscoree,+appwizcpl", "LANG": "en_US.UTF-8", "TMPDIR": home}


def wineboot_check(engine, timeout=900):
    """Returns (problems, detail). Kills everything the prefix started, whatever happens."""
    home = tempfile.mkdtemp(prefix="wineboot-")
    env = wine_env(engine, home)
    log = os.path.join(home, "wineboot.log")
    problems, start = [], time.time()
    with open(log, "w") as f:
        proc = subprocess.Popen([os.path.join(engine, "bin", "wine"), "wineboot", "--init"], env=env, stdout=f, stderr=subprocess.STDOUT)
    prompt = None
    try:
        while True:
            text = open(log, errors="replace").read()
            for marker in ("Got URL", "mono runtime not found"):
                if marker in text:
                    prompt = marker
            if prompt or proc.poll() is not None or time.time() - start > timeout:
                break
            time.sleep(2)
        if prompt:
            problems.append(f"a Mono or Gecko install prompt started (log: '{prompt}')")
        elif proc.poll() is None:
            problems.append(f"wineboot --init did not finish in {timeout} s")
        else:
            w = out([os.path.join(engine, "bin", "wineserver"), "-w"], env=env, timeout=300)
            if proc.returncode != 0:
                problems.append(f"wineboot --init exited {proc.returncode}")
            text = open(log, errors="replace").read()
            if "mono runtime is at" not in text:
                problems.append("the log does not show Wine finding its Mono runtime")
            if not os.path.isfile(os.path.join(env["WINEPREFIX"], "system.reg")):
                problems.append("no system.reg in the new prefix")
    finally:
        out([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, timeout=60)
        if proc.poll() is None:
            proc.kill()
    tail = open(log, errors="replace").read().splitlines()[-15:]
    shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-wineboot-last.log"))
    return problems, f"wineboot --init in a fresh prefix took {time.time() - start:.0f} s", tail


def version_check(engine, expected):
    home = tempfile.mkdtemp(prefix="wineversion-")
    r = out([os.path.join(engine, "bin", "wine"), "--version"], env=wine_env(engine, home), timeout=120)
    got = r.stdout.strip()
    if got != expected:
        return [f"wine --version printed '{got}' (exit {r.returncode}), expected '{expected}'"], got
    return [], got


def gate_wine(engine, ctx):
    problems, got = version_check(engine, ctx["expected_version"])
    boot, detail, tail = wineboot_check(engine)
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
    gst = out([exe, "gst", os.path.join(lib, "libgstreamer-1.0.0.dylib")] + GST_ELEMENTS, env=env, timeout=300)
    ff = out([exe, "ffmpeg", os.path.join(lib, "libavcodec.61.dylib")] + FFMPEG_DECODERS, env=env, timeout=120)
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


GATES = [("relocatable", gate_relocatable), ("dlopen", gate_dlopen), ("pe32", gate_pe32),
         ("winemac", gate_winemac), ("addons", gate_addons), ("wine", gate_wine),
         ("media", gate_media), ("licences", gate_licences), ("nogpl", gate_nogpl)]


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


def run_gates(engine, work):
    ctx = context(work)
    engine = os.path.abspath(engine)
    results = []
    for name, fn in GATES:
        t = time.time()
        try:
            ok, detail, problems = fn(engine, ctx)
        except Exception as e:  # a gate that cannot run is a failed gate
            ok, detail, problems = False, f"the gate itself failed: {e!r}", [repr(e)]
        results.append({"gate": name, "result": "PASS" if ok else "FAIL", "detail": detail,
                        "problems": problems, "seconds": round(time.time() - t, 1)})
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({time.time() - t:.0f} s) {detail}", flush=True)
        for p in problems[:30]:
            print("   " + p)
    os.makedirs(os.path.join(ctx["work"], "gates"), exist_ok=True)
    json.dump(results, open(os.path.join(ctx["work"], "gates", "results.json"), "w"), indent=2)
    report(results, "Gates")
    return all(r["result"] == "PASS" for r in results)


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
