"""Self-test for the gates: each gate is fed a bad input and must fail on it.

Called by `gates.py selftest ENGINE WORK` after the real gates passed. The bad inputs are small
made-up files, or an APFS clone of the engine with one thing broken, in a scratch folder. Each bad
input breaks only the property its gate checks, and every problem the gate reports must be about
that property (the case's `expect` pattern): a gate that failed for another reason would prove
nothing about the check the case names.
"""
import os
import re
import shutil
import subprocess
import tempfile

import gates as G

LIB_C = "int mavrik_selftest_value(void) { return 1; }\n"
# CrossOver's loader Info.plist (CrossOver Hack 10913), as the CrossOver tree has it.
CX_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>wineloader</string><!-- CrossOver Hack 10913 -->
    <key>CFBundleIdentifier</key>
    <string>com.codeweavers.CrossOver.wineloader</string><!-- CrossOver Hack 10913 -->
    <key>CFBundleName</key>
    <string>CrossOver-Hosted Application</string><!-- CrossOver Hack 10913 -->
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>
"""
# The CrossOver tree's crash-dialog link (programs/winedbg/winedbg.rc).
CX_CRASH_LINK = 'then <a href="https://www.codeweavers.com/support/tickets/enter/">file a bug report</a>'
USER_C = "int mavrik_selftest_value(void);\nint mavrik_selftest_user(void) { return mavrik_selftest_value(); }\n"


def cc(src_text, out_path, *args):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    src = out_path + ".c"
    open(src, "w").write(src_text)
    subprocess.run(["clang", "-arch", "x86_64", "-dynamiclib", "-o", out_path, src] + list(args), check=True)
    os.remove(src)


def clone(src, dest):
    subprocess.run(["cp", "-c", "-R", src, dest], check=True)


def case(results, gate, bad_input, problems, expect):
    """The gate must fail on the bad input, and only for the reason the case names (expect, a regex
    every problem must match)."""
    problems = [str(p) for p in problems]
    other = [p for p in problems if not re.search(expect, p)]
    if not problems:
        verdict, why = "DID NOT FAIL", ["the gate passed a bad input"]
    elif other:
        verdict, why = "FAILED FOR ANOTHER REASON", [f"not about /{expect}/: {p}" for p in other[:5]]
    else:
        verdict, why = "failed as it must", []
    results.append({"gate": gate, "result": "PASS" if not why else "FAIL", "detail": f"{bad_input}: {verdict}",
                    "problems": why, "evidence": problems[:3]})
    print(f"selftest {gate}: {bad_input} -> {verdict}")
    for p in (problems[:3] + why)[:6]:
        print("   " + p)


def skipped(results, gate, bad_input, reason):
    results.append({"gate": gate, "result": "SKIP", "detail": f"{bad_input}: not run ({reason})", "problems": [],
                    "evidence": []})
    print(f"selftest {gate}: {bad_input} -> not run ({reason})")


def run(engine, work):
    engine = os.path.abspath(engine)
    ctx = G.context(work)
    tmp = tempfile.mkdtemp(prefix="gate-selftest-")
    results = []

    # relocatable: a library with an absolute run path into Homebrew.
    fake = os.path.join(tmp, "reloc", "lib", "libfake.dylib")
    cc(LIB_C, fake, "-install_name", "@rpath/libfake.dylib")
    ok, _, problems = G.gate_relocatable(os.path.join(tmp, "reloc"), ctx)
    if not ok:
        raise SystemExit(f"selftest setup: the clean fake library should pass, got {problems}")
    subprocess.run(["install_name_tool", "-add_rpath", "/usr/local/opt/fake/lib", fake], check=True)
    subprocess.run(["codesign", "-f", "-s", "-", fake], check=True, capture_output=True)
    case(results, "relocatable", "a library with the run path /usr/local/opt/fake/lib",
         G.gate_relocatable(os.path.join(tmp, "reloc"), ctx)[2], r"LC_RPATH /usr/local/opt/fake/lib")

    # dlopen: a bundled library that needs one left behind in a build folder, which is masked.
    build_only = os.path.join(tmp, "build-only")
    dep = os.path.join(build_only, "libdep.dylib")
    cc(LIB_C, dep, "-install_name", dep)
    user = os.path.join(tmp, "dl", "lib", "libuser.dylib")
    cc(USER_C, user, "-install_name", "@rpath/libuser.dylib", dep)
    case(results, "dlopen", "a library linking one that only exists in a masked build folder",
         G.gate_dlopen(os.path.join(tmp, "dl"), dict(ctx, mask=[build_only]))[2], r"libuser\.dylib|libdep\.dylib")

    # pe32: the engine's whole i386-windows folder, with the 64-bit ntdll.dll where the 32-bit one belongs.
    d32 = os.path.join(tmp, "pe", "lib", "wine", "i386-windows")
    os.makedirs(os.path.dirname(d32))
    clone(os.path.join(engine, "lib", "wine", "i386-windows"), d32)
    os.remove(os.path.join(d32, "ntdll.dll"))
    shutil.copy(os.path.join(engine, "lib", "wine", "x86_64-windows", "ntdll.dll"), os.path.join(d32, "ntdll.dll"))
    case(results, "pe32", "the full i386-windows folder with a 64-bit ntdll.dll", G.gate_pe32(os.path.join(tmp, "pe"), ctx)[2],
         r"ntdll\.dll is machine 0x8664")

    # winemac: a winemac.so without macdrv_functions; and the engine's own with a changed layout.
    cx = os.path.join(ctx["work"], "wine-src", "dlls", "winemac.drv", "d3dmetal.c")
    dxmt = ctx["paths"]["dxmt-winemetal-source"]
    bare = os.path.join(tmp, "winemac", "winemac.so")
    cc(LIB_C, bare)
    case(results, "winemac", "a winemac.so that exports no macdrv_functions", G.winemac_check(bare, cx, dxmt)[0],
         r"does not export _macdrv_functions")
    swapped = os.path.join(tmp, "winemac", "d3dmetal.c")
    text = open(cx).read()
    a = "    struct d3dmetal_macdrv_win_data* (*get_win_data)(HWND hwnd);\n"
    b = "    void (*release_win_data)(struct d3dmetal_macdrv_win_data *data);\n"
    if a + b not in text:
        raise SystemExit("selftest setup: d3dmetal.c no longer has the expected macdrv_functions lines")
    open(swapped, "w").write(text.replace(a + b, b + a))
    case(results, "winemac", "the engine's winemac.so with get_win_data and release_win_data swapped in the source",
         G.winemac_check(os.path.join(engine, "lib", "wine", "x86_64-unix", "winemac.so"), swapped, dxmt)[0],
         r"macdrv_functions layout differs")

    # addons: addons.c naming an unpinned Mono; an engine with no Gecko.
    bad_addons = os.path.join(tmp, "addons.c")
    real = open(os.path.join(ctx["work"], "wine-src", "dlls", "appwiz.cpl", "addons.c")).read()
    open(bad_addons, "w").write(real.replace('#define MONO_VERSION "', '#define MONO_VERSION "0.0.1-not-'))
    case(results, "addons", "addons.c naming Wine Mono 0.0.1-not-...", G.addons_source_problems(bad_addons, ctx["inputs"])[0],
         r"asks for Wine Mono 0\.0\.1-not-")
    no_gecko = os.path.join(tmp, "addons-engine")
    os.makedirs(os.path.join(no_gecko, "share", "wine"))
    clone(os.path.join(engine, "share", "wine", "mono"), os.path.join(no_gecko, "share", "wine", "mono"))
    case(results, "addons", "an engine with Mono but no Gecko", G.gate_addons(no_gecko, ctx)[2], r"wine-gecko-[\d.]+-x86(_64)?: 0 files")

    # wine: a wrong expected version; an engine clone without Mono and Gecko, which must prompt at
    # wineboot; one with Mono but no Gecko, which must prompt when mshtml loads Gecko; and one
    # without its GnuTLS, which Wine's own code must then fail to load from the engine.
    gecko = ctx["inputs"]["inputs"]["wine-gecko-x86"]["version"]
    case(results, "wine", "expecting wine-0.0", G.version_check(engine, "wine-0.0")[0], r"expected 'wine-0\.0'")
    bad = os.path.join(tmp, "no-addons-engine")
    clone(engine, bad)
    shutil.rmtree(os.path.join(bad, "share", "wine", "mono"))
    shutil.rmtree(os.path.join(bad, "share", "wine", "gecko"))
    case(results, "wine", "wineboot on an engine clone without Mono and Gecko", G.wineboot_check(bad, gecko, timeout=600)[0],
         r"Mono or Gecko install prompt")
    shutil.rmtree(bad, ignore_errors=True)
    bad = os.path.join(tmp, "no-gecko-engine")
    clone(engine, bad)
    shutil.rmtree(os.path.join(bad, "share", "wine", "gecko"))
    case(results, "wine", "an engine clone with Mono but no Gecko", G.wineboot_check(bad, gecko, timeout=600)[0],
         r"Wine Gecko \(x86_64\) started a download prompt")
    shutil.rmtree(bad, ignore_errors=True)
    # Without its GnuTLS, Wine finds none on a Mac that has none, or, on a Mac with one in dyld's
    # fallback folders (Homebrew in /usr/local, as on GitHub's Intel runner), loads that one.
    # Either way the gate must fail.
    probes, required = G.winelibs_inputs(ctx)
    gnutls = next(r for r in required if os.path.basename(r).startswith("libgnutls"))
    bad = os.path.join(tmp, "no-gnutls-engine")
    clone(engine, bad)
    os.remove(os.path.join(bad, gnutls))
    case(results, "wine", f"an engine clone without {gnutls}",
         G.wineboot_check(bad, gecko, timeout=600, probes=probes, required=required)[0],
         r"bcrypt-aes|schannel|gnutls|loaded /(usr/local|opt/homebrew)/")
    shutil.rmtree(bad, ignore_errors=True)

    # media: a plugin with a run path into the Mac's own GStreamer.framework, in a clone of the engine's
    # lib folder, where every library it links is found.
    os.makedirs(os.path.join(tmp, "media"))
    clone(os.path.join(engine, "lib"), os.path.join(tmp, "media", "lib"))
    plug = os.path.join(tmp, "media", "lib", "gstreamer-1.0", "libgstapp.dylib")
    os.chmod(plug, 0o644)
    subprocess.run(["install_name_tool", "-add_rpath", G.GST_FRAMEWORK + "/Versions/1.0/lib", plug], check=True,
                   capture_output=True)
    case(results, "media", "a plugin with a run path into /Library/Frameworks/GStreamer.framework",
         G.media_static(os.path.join(tmp, "media"), [plug]), r"LC_RPATH /Library/Frameworks/GStreamer\.framework")
    # media and dlopen: the dyld check behind "nothing loads from outside the engine" (and so from
    # GStreamer.framework). The media gate's own run, judged as if the engine were somewhere else,
    # must be reported; if dyld's output stopped parsing, this would find nothing and fail here.
    gst_run = open(os.path.join(ctx["work"], "gates", "mediacheck-gst.txt")).read().split("\n--- stderr ---\n")[-1]
    case(results, "media", "the media gate's GStreamer loads, judged as if the engine were elsewhere",
         G.outside(G.dyld_images(gst_run), os.path.join(tmp, "elsewhere"), [os.path.join(ctx["work"], "tools", "mediacheck")]),
         re.escape(os.path.realpath(engine)))

    # licences: an engine clone with one stray file.
    lic = os.path.join(tmp, "licence-engine")
    clone(engine, lic)
    open(os.path.join(lic, "lib", "libstray.dylib"), "w").write("stray")
    case(results, "licences", "an engine clone with lib/libstray.dylib added", G.licence_problems(lic)[0],
         r"not covered by licences/FILES\.tsv: lib/libstray\.dylib")
    shutil.rmtree(lic, ignore_errors=True)

    # nogpl: a GPL plugin in the registry; an FFmpeg built with --enable-gpl; an x264 library.
    gst = "plugin\tx264\tGPL\t/somewhere/libgstx264.dylib\n"
    ff_ok = open(os.path.join(ctx["work"], "gates", "mediacheck-ffmpeg.txt")).read()
    case(results, "nogpl", "a plugin declaring GPL", G.nogpl_problems(engine, gst, ff_ok)[0], r"plugin x264 declares licence GPL")
    case(results, "nogpl", "FFmpeg configured with --enable-gpl",
         G.nogpl_problems(engine, "", "license\tGPL version 2 or later\nconfiguration\t--enable-gpl\n")[0],
         r"FFmpeg (says license\tGPL|was configured with --enable-gpl)")
    gpl_engine = os.path.join(tmp, "gpl-engine")
    os.makedirs(os.path.join(gpl_engine, "lib", "gstreamer-1.0"))
    shutil.copytree(os.path.join(engine, "licences"), os.path.join(gpl_engine, "licences"))
    open(os.path.join(gpl_engine, "lib", "gstreamer-1.0", "libgstx264.dylib"), "w").write("x")
    case(results, "nogpl", "lib/gstreamer-1.0/libgstx264.dylib present", G.nogpl_problems(gpl_engine, "", ff_ok)[0],
         r"libgstx264\.dylib")

    # identity: a loader carrying CrossOver's Info.plist; a crash dialog sending people to CodeWeavers.
    ident = os.path.join(tmp, "identity")
    loader = os.path.join(ident, G.LOADER)
    os.makedirs(os.path.dirname(loader))
    open(loader + ".plist", "w").write(CX_PLIST)
    open(loader + ".c", "w").write("int main(void) { return 0; }\n")
    subprocess.run(["clang", "-arch", "x86_64", "-o", loader, loader + ".c",
                    "-Wl,-sectcreate,__TEXT,__info_plist," + loader + ".plist"], check=True)
    os.remove(loader + ".c")
    os.remove(loader + ".plist")
    case(results, "identity", "a loader with CrossOver's Info.plist", G.identity_problems(ident, [G.LOADER])[0],
         r"CrossOver|codeweavers")
    winedbg = "lib/wine/x86_64-windows/winedbg.exe"
    bad_dbg = os.path.join(tmp, "identity-dbg")
    os.makedirs(os.path.join(bad_dbg, os.path.dirname(winedbg)))
    os.makedirs(os.path.dirname(os.path.join(bad_dbg, G.LOADER)))
    clone(os.path.join(engine, G.LOADER), os.path.join(bad_dbg, G.LOADER))
    data = open(os.path.join(engine, winedbg), "rb").read() + CX_CRASH_LINK.encode("utf-16-le")
    open(os.path.join(bad_dbg, winedbg), "wb").write(data)
    case(results, "identity", "winedbg.exe with CrossOver's crash-dialog link",
         G.identity_problems(bad_dbg, [G.LOADER, winedbg])[0], r"codeweavers\.com/support")

    # buildpaths: a library with the work folder's path compiled in.
    bp = os.path.join(tmp, "buildpaths", "lib", "libpath.dylib")
    needles = G.build_paths(ctx)
    cc(f'const char *mavrik_selftest_path = "{needles[-1]}/deps/etc/gnutls/config";\n' + LIB_C, bp)
    case(results, "buildpaths", "a library naming the work folder",
         G.buildpath_problems(os.path.join(tmp, "buildpaths"), needles)[0],
         r"libpath\.dylib contains .*" + re.escape(needles[-1]))

    # d3d11: an engine clone without DXMT's Unix side (winemetal.so), where Direct3D 11 cannot reach Metal.
    if G.metal_device(ctx["work"]):
        bad = os.path.join(tmp, "no-winemetal-engine")
        clone(engine, bad)
        os.remove(os.path.join(bad, "lib", "wine", "x86_64-unix", "winemetal.so"))
        case(results, "d3d11", "an engine clone without lib/wine/x86_64-unix/winemetal.so", G.d3d11_check(bad, ctx)[0],
             r"d3d11probe64\.exe: (device|present|readback) failed|d3d11probe64\.exe did not run to the end|winemetal\.so")
        shutil.rmtree(bad, ignore_errors=True)
    else:
        skipped(results, "d3d11", "an engine clone without winemetal.so", "this machine has no Metal device")

    # playback: an engine clone without GStreamer's FFmpeg plugin, so no H.264 or AAC decoder.
    bad = os.path.join(tmp, "no-libav-engine")
    clone(engine, bad)
    os.remove(os.path.join(bad, "lib", "gstreamer-1.0", "libgstlibav.dylib"))
    case(results, "playback", "an engine clone without lib/gstreamer-1.0/libgstlibav.dylib", G.playback_check(bad, ctx)[0],
         r"mediaprobe(32|64)\.exe: (mf|wm)-(video|audio) failed|libgstlibav\.dylib")
    shutil.rmtree(bad, ignore_errors=True)

    shutil.rmtree(tmp, ignore_errors=True)
    covered = {r["gate"] for r in results}
    missing = [name for name, _ in G.GATES if name not in covered]
    if missing:
        results.append({"gate": "selftest", "result": "FAIL", "detail": "gates with no bad-input case: " + ", ".join(missing),
                        "problems": missing})
    G.report(results, "Gate self-test (each gate must fail on a bad input, for that gate's reason)")
    import json
    json.dump(results, open(os.path.join(ctx["work"], "gates", "selftest.json"), "w"), indent=2)
    return all(r["result"] in ("PASS", "SKIP") for r in results)
