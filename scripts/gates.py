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
  d3d11         a Windows program draws through Direct3D 11 on a visible window: DXMT's device,
                60 frames presented into its Metal view, and a GPU readback; winemetal.so and
                winemac.so load from the engine. A machine with no Metal device (GitHub's Intel
                runners are virtual machines without one) reports SKIP, never PASS
  playback      a Windows program decodes a movie (H.264 and AAC in MP4) in both halves through Media
                Foundation and through the Windows Media reader; GStreamer's plugins load from the
                engine's lib/gstreamer-1.0, and nothing from outside the engine and macOS

A gate returns PASS, FAIL or, for d3d11 only, SKIP with its reason.
"""
import fnmatch
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

from assemble import NOT_CARRIED

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
    # GStreamer's plugin list goes in this home, as the README asks of any program that starts the engine.
    return {"PATH": f"{engine}/bin:/usr/bin:/bin", "HOME": home, "WINEPREFIX": os.path.join(home, "prefix"),
            "WINEDEBUG": "fixme-all,+mscoree,+appwizcpl", "LANG": "en_US.UTF-8", "TMPDIR": home,
            "GST_REGISTRY_1_0": os.path.join(home, "gst-registry.bin"), "WINEARCH": "wow64"}


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
        proc.wait()
    return prompt, code, text


def winelibs_inputs(ctx):
    """The winelibs probe for each Windows half, and the engine files Wine's own code must load when
    it runs: every library Wine opens by file name (config.h's SONAME_* values, less the ones the
    engine does not carry) and the Unix modules that link GStreamer and FFmpeg."""
    probes = [compile_pe_tool(ctx["work"], "winelibs", bits, ["bcrypt", "secur32", "gdi32", "user32"])
              for bits in ("64", "32")]
    config = open(os.path.join(ctx["work"], "wine-install", ".build", "config.h")).read()
    names = sorted({v for k, v in re.findall(r'^#define (SONAME_\w+) "([^"]+)"$', config, re.M) if k not in NOT_CARRIED})
    return probes, ["lib/" + n for n in names] + [f"lib/wine/x86_64-unix/{m}.so" for m in ("winegstreamer", "winedmo")]


def wineboot_check(engine, gecko_version, timeout=900, probes=(), required=()):
    """wineboot --init in a fresh prefix must finish with no download prompt and find the engine's
    Mono; then Wine Gecko must load from the engine in both halves (regsvr32 /i mshtml.dll makes
    mshtml load it, as a game's first web view would); then every check of each probe
    (winelibs_inputs) must pass. dyld lists the libraries every Wine process loads: none may come from
    outside the engine and macOS, and once the probes have run, each of `required` (paths in the
    engine) must be among them. Returns (problems, detail, log tail). Kills everything the prefix
    started and removes the prefix, whatever happens."""
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
            out([os.path.join(engine, "bin", "wineserver"), "-w"], env=env, timeout=300)
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
        # Stop every process the prefix started, then read what dyld printed for each of them.
        out([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, timeout=60)
        images = dyld_images(open(log, errors="replace").read())
        if not images:
            problems.append("dyld listed no libraries: the trace this gate reads is missing")
        problems += [f"a Wine process loaded {img}, outside the engine and macOS" for img in outside(images, engine)]
        if probes and ran == len(probes):
            seen = {os.path.realpath(i) for i in images}
            problems += [f"Wine's own code did not load {r} from the engine" for r in required
                         if os.path.realpath(os.path.join(engine, r)) not in seen]
    finally:
        out([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, timeout=60)
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


def run_probes(wine, probes, env, log, timeout=300):
    """Runs each (Windows program, arguments) with Wine. Returns (problems, the probes whose every check
    passed, how many ran to the end): every "check" line must say ok, and each must print "done"."""
    problems, probed, ran = [], [], 0
    for probe, args in probes:
        name = os.path.basename(probe)
        prompt, code, text = run_watched([wine, probe] + list(args), dict(env, WINEDEBUG="fixme-all"), log, timeout)
        lines = text.splitlines()
        checks = [l.split("\t") for l in lines if l.startswith("check\t")]
        problems += [f"{name}: {c[1]} failed ({c[3] if len(c) > 3 else '?'})" for c in checks if c[2:3] != ["ok"]]
        if any(l.startswith("done\t") for l in lines) and checks:
            ran += 1
            if all(c[2:3] == ["ok"] for c in checks):
                probed.append(f"{name}: " + "; ".join(f"{c[1]} {c[3] if len(c) > 3 else ''}".strip() for c in checks))
        else:
            problems.append(f"{name} did not run to the end (exit {code}{', timed out' if code is None else ''})")
    return problems, probed, ran


def probe_check(engine, probes, required=(), timeout=900):
    """A fresh prefix (wineboot --init), then each (Windows program, arguments) of probes. dyld lists
    what every Wine process loads: nothing may come from outside the engine and macOS, and once every
    probe ran to the end, each of `required` (paths in the engine) must be among the loaded images.
    Returns (problems, the probes' results, the engine's loaded images). Kills everything the prefix
    started and removes it, whatever happens."""
    home = tempfile.mkdtemp(prefix="probe-")
    env = dict(wine_env(engine, home), DYLD_PRINT_LIBRARIES="1")
    wine = os.path.join(engine, "bin", "wine")
    log = os.path.join(home, "probe.log")
    problems, probed, images = [], [], []
    try:
        prompt, code, _ = run_watched([wine, "wineboot", "--init"], env, log, timeout)
        if prompt or code != 0:
            problems.append(f"wineboot --init: {prompt or 'exit %s' % code}")
        else:
            # A probe that crashes must end, not wait behind Wine's crash dialog.
            run_watched([wine, "reg", "add", "HKCU\\Software\\Wine\\WineDbg", "/v", "ShowCrashDialog",
                         "/t", "REG_DWORD", "/d", "0", "/f"], env, log, 120)
            out([os.path.join(engine, "bin", "wineserver"), "-w"], env=env, timeout=300)
            p, probed, ran = run_probes(wine, probes, env, log)
            problems += p
        out([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, timeout=60)
        images = dyld_images(open(log, errors="replace").read())
        if not images:
            problems.append("dyld listed no libraries: the trace this gate reads is missing")
        problems += [f"a Wine process loaded {img}, outside the engine and macOS" for img in outside(images, engine)]
        if not problems:
            seen = {os.path.realpath(i) for i in images}
            problems += [f"Wine did not load {r} from the engine" for r in required
                         if os.path.realpath(os.path.join(engine, r)) not in seen]
    finally:
        out([os.path.join(engine, "bin", "wineserver"), "-k"], env=env, timeout=60)
        if os.path.exists(log):
            shutil.copy(log, os.path.join(tempfile.gettempdir(), "mavrik-probe-last.log"))
        shutil.rmtree(home, ignore_errors=True)
    root = os.path.realpath(engine) + "/"
    loaded = sorted({os.path.relpath(os.path.realpath(i), root) for i in images if os.path.realpath(i).startswith(root)})
    return problems, probed, loaded


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


def d3d11_check(engine, ctx):
    probe = compile_pe_tool(ctx["work"], "d3d11probe", "64", ["d3d11", "dxgi", "uuid", "gdi32", "user32"])
    required = ["lib/wine/x86_64-unix/winemetal.so", "lib/wine/x86_64-unix/winemac.so"]
    problems, probed, loaded = probe_check(engine, [(probe, [])], required)
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


GATES = [("relocatable", gate_relocatable), ("dlopen", gate_dlopen), ("pe32", gate_pe32),
         ("winemac", gate_winemac), ("addons", gate_addons), ("wine", gate_wine),
         ("media", gate_media), ("licences", gate_licences), ("nogpl", gate_nogpl),
         ("identity", gate_identity), ("buildpaths", gate_buildpaths), ("d3d11", gate_d3d11),
         ("playback", gate_playback)]


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
        result = "SKIP" if ok is None else "PASS" if ok else "FAIL"
        results.append({"gate": name, "result": result, "detail": detail,
                        "problems": problems, "seconds": round(time.time() - t, 1)})
        print(f"{name}: {result} ({time.time() - t:.0f} s) {detail}", flush=True)
        for p in problems[:30]:
            print("   " + p)
    os.makedirs(os.path.join(ctx["work"], "gates"), exist_ok=True)
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
