#!/usr/bin/env python3
"""The Steam bridge's gates: checks that fail its build, and a self-test that shows each one failing.

  bridge/bridgegates.py run BRIDGE WORK        run every gate on the folder bridge/assemble.py made
  bridge/bridgegates.py selftest BRIDGE WORK   show that every gate fails on a bad input, for its own reason

WORK is the engine's work folder: the engine scripts/build.sh and assemble.sh made there
(WORK/out/<name>) is the one the bridge is gated with. Results go to WORK/bridge/gates/.

The gates:
  files          exactly the five files, each what it must be: lsteamclient.dll and steam.exe as
                 Wine builtins, 32-bit (i386) in i386-windows and 64-bit (AMD64) in x86_64-windows;
                 lsteamclient.so a Mach-O for x86_64 only
  calltables     nm shows lsteamclient.so's two Unix call tables: __wine_unix_call_funcs (64-bit
                 callers) and __wine_unix_call_wow64_funcs (32-bit callers, in Wine's wow64 mode)
  unsigned       lsteamclient.so has no code signature (NotProton: "wine builtins fail to load once
                 codesigned"), as Wine's linker leaves its Unix modules
  links          lsteamclient.so loads only the engine's ntdll.so (@rpath/ntdll.so) and macOS's own
                 libraries, and its only run path is @loader_path/; nothing absolute outside
                 /usr/lib and /System
  licences       every file is covered by licences/FILES.tsv and every component has its texts; the
                 lsteamclient files are labelled lsteamclient (the Steamworks SDK licence) and
                 steam.exe steam-helper (BSD-3-Clause), never wine
  buildpaths     no file carries the build machine's work or recipe folder
  steamredirect  the engine's loader with the real lsteamclient: on an APFS clone of the engine with
                 the bridge's files added (as a launcher adds them), a Windows program in each half
                 loads a stand-in steamclient DLL, its export jumps into lsteamclient, whose Windows
                 half calls its Unix half through the 64-bit or the wow64 call table, and the answer
                 comes back (bridge/tools/bridgeprobe.c). STEAM_COMPAT_CLIENT_INSTALL_PATH points at
                 an empty folder, so no Steam library is loaded and no Steam app is touched
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gates as G  # noqa: E402  (the engine's gates: helpers reused, nothing changed)
from licences import BRIDGE_FILES  # noqa: E402

PE = {"lib/wine/i386-windows/lsteamclient.dll": 0x14c, "lib/wine/x86_64-windows/lsteamclient.dll": 0x8664,
      "lib/wine/i386-windows/steam.exe": 0x14c, "lib/wine/x86_64-windows/steam.exe": 0x8664}
UNIX = "lib/wine/x86_64-unix/lsteamclient.so"
TABLES = ["___wine_unix_call_funcs", "___wine_unix_call_wow64_funcs"]
MACHINES = {0x14c: "i386", 0x8664: "AMD64"}


def files_problems(bridge):
    problems = []
    have = sorted(os.path.relpath(p, bridge) for p in G.walk(os.path.join(bridge, "lib")))
    want = sorted(list(PE) + [UNIX])
    problems += [f"missing: {f}" for f in want if f not in have]
    problems += [f"not one of the bridge's files: {f}" for f in have if f not in want]
    for rel, machine in PE.items():
        path = os.path.join(bridge, rel)
        if not os.path.isfile(path):
            continue
        got = G.pe_machine(path)[0]
        if got != machine:
            problems.append(f"{rel} is {MACHINES.get(got, got)}, not {MACHINES[machine]}")
        if b"Wine builtin DLL" not in open(path, "rb").read(0x80):
            problems.append(f"{rel} is not a Wine builtin")
    path = os.path.join(bridge, UNIX)
    if os.path.isfile(path):
        archs = G.out(["lipo", "-archs", path]).stdout.split()
        if archs != ["x86_64"]:
            problems.append(f"{UNIX} is {archs or 'not a Mach-O'}, not x86_64 only")
    return problems


def gate_files(bridge, ctx):
    problems = files_problems(bridge)
    return not problems, "both Windows halves of lsteamclient and steam.exe as Wine builtins, and the x86_64 Unix half", problems


def calltables_problems(so):
    symbols = set(G.out(["nm", "-gU", so]).stdout.split())
    return [f"{os.path.basename(so)} does not export {t}" for t in TABLES if t not in symbols]


def gate_calltables(bridge, ctx):
    problems = calltables_problems(os.path.join(bridge, UNIX))
    return not problems, f"nm -gU: {', '.join(TABLES)}", problems


def signature_problems(so):
    r = G.out(["codesign", "-dv", so])
    if "not signed at all" in r.stderr:
        return []
    kind = next((l.split("=", 1)[1] for l in r.stderr.splitlines() if l.startswith("Signature=")), r.stderr.strip()[-120:])
    return [f"{os.path.basename(so)} is signed ({kind})"]


def gate_unsigned(bridge, ctx):
    problems = signature_problems(os.path.join(bridge, UNIX))
    return not problems, f"{UNIX}: code object is not signed at all", problems


def links_problems(so):
    problems = []
    for kind, value in G.macho_paths(so):
        if kind == "LC_ID_DYLIB":
            continue
        if kind == "LC_RPATH":
            if value != "@loader_path/":
                problems.append(f"{os.path.basename(so)} has the run path {value}")
        elif not (value == "@rpath/ntdll.so" or value.startswith(G.SYSTEM_PREFIXES)):
            problems.append(f"{os.path.basename(so)} loads {value}, which is neither the engine's ntdll.so nor macOS's")
    return problems


def gate_links(bridge, ctx):
    problems = links_problems(os.path.join(bridge, UNIX))
    return not problems, "loads @rpath/ntdll.so and macOS's libraries only; run path @loader_path/", problems


def bridge_licence_problems(bridge):
    problems, count = G.licence_problems(bridge)
    try:
        rows = G.read_tsv(os.path.join(bridge, "licences", "FILES.tsv"))
    except OSError:
        return problems, count
    for rel, comp in ((r[0], r[1]) for r in rows):
        want = BRIDGE_FILES.get(os.path.basename(rel))
        if want and comp != want:
            problems.append(f"{rel} is labelled {comp}, but it is {want}'s")
    return problems, count


def gate_licences(bridge, ctx):
    problems, count = bridge_licence_problems(bridge)
    return not problems, f"{count} files, all covered and labelled by their part", problems


def gate_buildpaths(bridge, ctx):
    needles = G.build_paths(ctx)
    problems, count = G.buildpath_problems(bridge, needles)
    return not problems, f"{count} files, none names {' or '.join(needles)}", problems


def probes(work):
    """For each half, a folder holding bridgeprobeNN.exe and the stand-in steamclient DLL beside it."""
    src = os.path.join(HERE, "tools", "bridgeprobe.c")
    found = []
    for bits, client in (("64", "steamclient64"), ("32", "steamclient")):
        folder = os.path.join(work, "bridge", "tools", "steamredirect" + bits)
        os.makedirs(folder, exist_ok=True)
        for name, extra in ((client + ".dll", ["-DPROBE_DLL", "-shared"]), (f"bridgeprobe{bits}.exe", [])):
            path = os.path.join(folder, name)
            if G.stale(path, src):
                subprocess.run([G.PE_COMPILERS[bits], "-O1", "-s"] + extra + ["-o", path, src], check=True)
        found.append(os.path.join(folder, f"bridgeprobe{bits}.exe"))
    return found


def with_engine(bridge, ctx, files=None):
    """An APFS clone of the engine with the bridge's files (or `files`, a subset) added to its lib/wine,
    as a launcher adds them. Returns its path; the caller removes it."""
    root = tempfile.mkdtemp(prefix="bridge-engine-", dir=os.path.join(ctx["work"], "bridge"))
    engine = os.path.join(root, os.path.basename(ctx["engine"]))
    subprocess.run(["cp", "-c", "-R", ctx["engine"], engine], check=True)
    for rel in (files if files is not None else list(PE) + [UNIX]):
        shutil.copy(os.path.join(bridge, rel), os.path.join(engine, rel))
    return engine


def steamredirect_check(bridge, ctx, files=None, extra_env=None):
    engine = with_engine(bridge, ctx, files)
    empty = tempfile.mkdtemp(prefix="no-steam-", dir=os.path.dirname(engine))
    try:
        env = dict({"STEAM_COMPAT_CLIENT_INSTALL_PATH": empty}, **(extra_env or {}))
        problems, probed, loaded = G.probe_check(engine, [(p, []) for p in probes(ctx["work"])],
                                                 required=[UNIX], extra_env=env)
    finally:
        shutil.rmtree(os.path.dirname(engine), ignore_errors=True)
    return problems, probed


def gate_steamredirect(bridge, ctx):
    problems, probed = steamredirect_check(bridge, ctx)
    return not problems, "; ".join(probed) + f"; {UNIX} loaded", problems


GATES = [("files", gate_files), ("calltables", gate_calltables), ("unsigned", gate_unsigned), ("links", gate_links),
         ("licences", gate_licences), ("buildpaths", gate_buildpaths), ("steamredirect", gate_steamredirect)]


def context(work):
    ctx = G.context(work)
    ctx["engine"] = os.path.join(ctx["work"], "out", open(os.path.join(ctx["work"], "out", "name")).read().strip())
    return ctx


def run_gates(bridge, work):
    ctx = context(work)
    bridge = os.path.abspath(bridge)
    results = []
    for name, fn in GATES:
        t = time.time()
        try:
            ok, detail, problems = fn(bridge, ctx)
        except Exception as e:  # a gate that cannot run is a failed gate
            ok, detail, problems = False, f"the gate itself failed: {e!r}", [repr(e)]
        results.append({"gate": name, "result": "PASS" if ok else "FAIL", "detail": detail,
                        "problems": problems, "seconds": round(time.time() - t, 1)})
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({time.time() - t:.0f} s) {detail}", flush=True)
        for p in problems[:30]:
            print("   " + p)
    os.makedirs(os.path.join(ctx["work"], "bridge", "gates"), exist_ok=True)
    json.dump(results, open(os.path.join(ctx["work"], "bridge", "gates", "results.json"), "w"), indent=2)
    G.report(results, f"Steam bridge gates (with {os.path.basename(ctx['engine'])})")
    return all(r["result"] == "PASS" for r in results)


def selftest(bridge, work):
    """Each gate fed a bad input: a made-up file or a clone of the bridge with one thing broken. Every
    problem the gate reports must be about that one thing (selftest.case)."""
    import selftest as T
    bridge = os.path.abspath(bridge)
    ctx = context(work)
    tmp = tempfile.mkdtemp(prefix="bridge-selftest-", dir=os.path.join(ctx["work"], "bridge"))
    results = []

    def broken(label):
        bad = os.path.join(tmp, label, os.path.basename(bridge))
        os.makedirs(os.path.dirname(bad))
        T.clone(bridge, bad)
        return bad

    # files: the 64-bit lsteamclient.dll where the 32-bit one belongs.
    bad = broken("files")
    shutil.copy(os.path.join(bad, "lib/wine/x86_64-windows/lsteamclient.dll"), os.path.join(bad, "lib/wine/i386-windows/lsteamclient.dll"))
    T.case(results, "files", "the 64-bit lsteamclient.dll in i386-windows", files_problems(bad),
           r"^lib/wine/i386-windows/lsteamclient\.dll is AMD64, not i386$")

    # calltables: a Unix library that exports only the 64-bit table, so 32-bit callers have none.
    so = os.path.join(tmp, "calltables", "lsteamclient.so")
    T.cc("const void *__wine_unix_call_funcs[1] = { 0 };\n", so)
    T.case(results, "calltables", "a Unix library without __wine_unix_call_wow64_funcs", calltables_problems(so),
           r"does not export ___wine_unix_call_wow64_funcs$")

    # unsigned: the real Unix half, signed ad hoc.
    bad = broken("unsigned")
    subprocess.run(["codesign", "-s", "-", "-f", os.path.join(bad, UNIX)], check=True, capture_output=True)
    T.case(results, "unsigned", "lsteamclient.so signed ad hoc", signature_problems(os.path.join(bad, UNIX)),
           r"^lsteamclient\.so is signed \(adhoc\)$")

    # links: the real Unix half with an absolute run path added (as a Homebrew-linked build would have).
    bad = broken("links")
    subprocess.run(["install_name_tool", "-add_rpath", "/opt/homebrew/lib", os.path.join(bad, UNIX)], check=True, capture_output=True)
    T.case(results, "links", "lsteamclient.so with the run path /opt/homebrew/lib", links_problems(os.path.join(bad, UNIX)),
           r"has the run path /opt/homebrew/lib$")

    # licences: lsteamclient labelled wine, the S188 lab's mistake.
    bad = broken("licences")
    files = os.path.join(bad, "licences", "FILES.tsv")
    text = open(files).read()
    os.remove(files)  # a new file, not the clone's shared blocks
    open(files, "w").write(text.replace("lsteamclient.so\tlsteamclient", "lsteamclient.so\twine"))
    T.case(results, "licences", "lsteamclient.so labelled wine in FILES.tsv", bridge_licence_problems(bad)[0],
           r"^lib/wine/x86_64-unix/lsteamclient\.so is labelled wine, but it is lsteamclient's$")

    # buildpaths: a file naming the work folder.
    bad = broken("buildpaths")
    open(os.path.join(bad, "NOTICE.txt"), "a").write(f"built in {ctx['work']}/bridge/wine-build\n")
    T.case(results, "buildpaths", "NOTICE.txt naming the work folder", G.buildpath_problems(bad, G.build_paths(ctx))[0],
           r"^NOTICE\.txt contains ")

    # steamredirect: the bridge turned off with Valve's own switch, so lsteamclient never loads.
    T.case(results, "steamredirect", "the bridge turned off with PROTON_DISABLE_LSTEAMCLIENT=1",
           steamredirect_check(bridge, ctx, extra_env={"PROTON_DISABLE_LSTEAMCLIENT": "1"})[0],
           r"bridgeprobe(32|64)\.exe: redirect failed")
    # steamredirect: the Unix half left out, so lsteamclient's Windows half has nothing to call. The
    # check that it was loaded is left out too, since it cannot be.
    problems = steamredirect_check(bridge, ctx, files=list(PE))[0]
    T.case(results, "steamredirect", "the bridge's files without lsteamclient.so",
           [p for p in problems if UNIX not in p], r"bridgeprobe(32|64)\.exe: unixlib failed")

    shutil.rmtree(tmp, ignore_errors=True)
    missing = [name for name, _ in GATES if name not in {r["gate"] for r in results}]
    if missing:
        results.append({"gate": "selftest", "result": "FAIL", "detail": "gates with no bad-input case: " + ", ".join(missing),
                        "problems": missing})
    G.report(results, "Steam bridge gate self-test (each gate must fail on a bad input, for that gate's reason)")
    json.dump(results, open(os.path.join(ctx["work"], "bridge", "gates", "selftest.json"), "w"), indent=2)
    return all(r["result"] == "PASS" for r in results)


def main(argv):
    if len(argv) == 4 and argv[1] == "run":
        sys.exit(0 if run_gates(argv[2], argv[3]) else 1)
    if len(argv) == 4 and argv[1] == "selftest":
        sys.exit(0 if selftest(argv[2], argv[3]) else 1)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
