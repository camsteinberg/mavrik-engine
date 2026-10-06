"""Self-test for the gates: each gate is fed a bad input and must fail on it.

Called by `gates.py selftest ENGINE WORK` after the real gates passed. The bad inputs are small
made-up files, or an APFS clone of the engine with one thing broken, in a scratch folder.
"""
import os
import shutil
import subprocess
import tempfile

import gates as G

LIB_C = "int mavrik_selftest_value(void) { return 1; }\n"
USER_C = "int mavrik_selftest_value(void);\nint mavrik_selftest_user(void) { return mavrik_selftest_value(); }\n"


def cc(src_text, out_path, *args):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    src = out_path + ".c"
    open(src, "w").write(src_text)
    subprocess.run(["clang", "-arch", "x86_64", "-dynamiclib", "-o", out_path, src] + list(args), check=True)
    os.remove(src)


def clone(src, dest):
    subprocess.run(["cp", "-c", "-R", src, dest], check=True)


def case(results, gate, bad_input, problems):
    failed = bool(problems)
    results.append({"gate": gate, "result": "PASS" if failed else "FAIL",
                    "detail": f"{bad_input}: {'failed as it must' if failed else 'DID NOT FAIL'}",
                    "problems": [] if failed else ["the gate passed a bad input"],
                    "evidence": problems[:3]})
    print(f"selftest {gate}: {bad_input} -> {'fails (good)' if failed else 'PASSES (bad)'}")
    for p in problems[:3]:
        print("   " + str(p))


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
         G.gate_relocatable(os.path.join(tmp, "reloc"), ctx)[2])

    # dlopen: a bundled library that needs one left behind in a build folder, which is masked.
    build_only = os.path.join(tmp, "build-only")
    dep = os.path.join(build_only, "libdep.dylib")
    cc(LIB_C, dep, "-install_name", dep)
    user = os.path.join(tmp, "dl", "lib", "libuser.dylib")
    cc(USER_C, user, "-install_name", "@rpath/libuser.dylib", dep)
    case(results, "dlopen", "a library linking one that only exists in a masked build folder",
         G.gate_dlopen(os.path.join(tmp, "dl"), dict(ctx, mask=[build_only]))[2])

    # pe32: the 64-bit ntdll.dll where the 32-bit one belongs.
    d32 = os.path.join(tmp, "pe", "lib", "wine", "i386-windows")
    os.makedirs(d32)
    shutil.copy(os.path.join(engine, "lib", "wine", "x86_64-windows", "ntdll.dll"), os.path.join(d32, "ntdll.dll"))
    case(results, "pe32", "a 64-bit ntdll.dll in i386-windows", G.gate_pe32(os.path.join(tmp, "pe"), ctx)[2])

    # winemac: a winemac.so without macdrv_functions; and the engine's own with a changed layout.
    cx = os.path.join(ctx["work"], "wine-src", "dlls", "winemac.drv", "d3dmetal.c")
    dxmt = ctx["paths"]["dxmt-winemetal-source"]
    bare = os.path.join(tmp, "winemac", "winemac.so")
    cc(LIB_C, bare)
    case(results, "winemac", "a winemac.so that exports no macdrv_functions", G.winemac_check(bare, cx, dxmt)[0])
    swapped = os.path.join(tmp, "winemac", "d3dmetal.c")
    text = open(cx).read()
    a = "    struct d3dmetal_macdrv_win_data* (*get_win_data)(HWND hwnd);\n"
    b = "    void (*release_win_data)(struct d3dmetal_macdrv_win_data *data);\n"
    if a + b not in text:
        raise SystemExit("selftest setup: d3dmetal.c no longer has the expected macdrv_functions lines")
    open(swapped, "w").write(text.replace(a + b, b + a))
    case(results, "winemac", "the engine's winemac.so with get_win_data and release_win_data swapped in the source",
         G.winemac_check(os.path.join(engine, "lib", "wine", "x86_64-unix", "winemac.so"), swapped, dxmt)[0])

    # addons: addons.c naming an unpinned Mono; an engine with no Gecko.
    bad_addons = os.path.join(tmp, "addons.c")
    real = open(os.path.join(ctx["work"], "wine-src", "dlls", "appwiz.cpl", "addons.c")).read()
    open(bad_addons, "w").write(real.replace('#define MONO_VERSION "', '#define MONO_VERSION "0.0.1-not-'))
    case(results, "addons", "addons.c naming Wine Mono 0.0.1-not-...", G.addons_source_problems(bad_addons, ctx["inputs"])[0])
    no_gecko = os.path.join(tmp, "addons-engine")
    os.makedirs(os.path.join(no_gecko, "share", "wine"))
    clone(os.path.join(engine, "share", "wine", "mono"), os.path.join(no_gecko, "share", "wine", "mono"))
    case(results, "addons", "an engine with Mono but no Gecko", G.gate_addons(no_gecko, ctx)[2])

    # wine: a wrong expected version; an engine clone without Mono and Gecko, which must prompt at
    # wineboot; one with Mono but no Gecko, which must prompt when mshtml loads Gecko; and one
    # without its GnuTLS, which Wine's own code must then fail to load from the engine.
    gecko = ctx["inputs"]["inputs"]["wine-gecko-x86"]["version"]
    case(results, "wine", "expecting wine-0.0", G.version_check(engine, "wine-0.0")[0])
    bad = os.path.join(tmp, "no-addons-engine")
    clone(engine, bad)
    shutil.rmtree(os.path.join(bad, "share", "wine", "mono"))
    shutil.rmtree(os.path.join(bad, "share", "wine", "gecko"))
    case(results, "wine", "wineboot on an engine clone without Mono and Gecko", G.wineboot_check(bad, gecko, timeout=600)[0])
    shutil.rmtree(bad, ignore_errors=True)
    bad = os.path.join(tmp, "no-gecko-engine")
    clone(engine, bad)
    shutil.rmtree(os.path.join(bad, "share", "wine", "gecko"))
    case(results, "wine", "an engine clone with Mono but no Gecko", G.wineboot_check(bad, gecko, timeout=600)[0])
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
         G.wineboot_check(bad, gecko, timeout=600, probes=probes, required=required)[0])
    shutil.rmtree(bad, ignore_errors=True)

    # media: a plugin with a run path into the Mac's own GStreamer.framework.
    plug_dir = os.path.join(tmp, "media", "lib", "gstreamer-1.0")
    os.makedirs(plug_dir)
    plug = os.path.join(plug_dir, "libgstfake.dylib")
    shutil.copy(os.path.join(engine, "lib", "gstreamer-1.0", "libgstapp.dylib"), plug)
    os.chmod(plug, 0o644)
    subprocess.run(["install_name_tool", "-add_rpath", G.GST_FRAMEWORK + "/Versions/1.0/lib", plug], check=True)
    case(results, "media", "a plugin with a run path into /Library/Frameworks/GStreamer.framework",
         G.media_static(os.path.join(tmp, "media"), [plug]))
    # media and dlopen: the dyld check behind "nothing loads from outside the engine" (and so from
    # GStreamer.framework). The media gate's own run, judged as if the engine were somewhere else,
    # must be reported; if dyld's output stopped parsing, this would find nothing and fail here.
    gst_run = open(os.path.join(ctx["work"], "gates", "mediacheck-gst.txt")).read().split("\n--- stderr ---\n")[-1]
    case(results, "media", "the media gate's GStreamer loads, judged as if the engine were elsewhere",
         G.outside(G.dyld_images(gst_run), os.path.join(tmp, "elsewhere"), [os.path.join(ctx["work"], "tools", "mediacheck")]))

    # licences: an engine clone with one stray file.
    lic = os.path.join(tmp, "licence-engine")
    clone(engine, lic)
    open(os.path.join(lic, "lib", "libstray.dylib"), "w").write("stray")
    case(results, "licences", "an engine clone with lib/libstray.dylib added", G.licence_problems(lic)[0])
    shutil.rmtree(lic, ignore_errors=True)

    # nogpl: a GPL plugin in the registry; an FFmpeg built with --enable-gpl; an x264 library.
    gst = "plugin\tx264\tGPL\t/somewhere/libgstx264.dylib\n"
    ff_ok = open(os.path.join(ctx["work"], "gates", "mediacheck-ffmpeg.txt")).read()
    case(results, "nogpl", "a plugin declaring GPL", G.nogpl_problems(engine, gst, ff_ok)[0])
    case(results, "nogpl", "FFmpeg configured with --enable-gpl",
         G.nogpl_problems(engine, "", "license\tGPL version 2 or later\nconfiguration\t--enable-gpl\n")[0])
    gpl_engine = os.path.join(tmp, "gpl-engine")
    os.makedirs(os.path.join(gpl_engine, "lib", "gstreamer-1.0"))
    shutil.copytree(os.path.join(engine, "licences"), os.path.join(gpl_engine, "licences"))
    open(os.path.join(gpl_engine, "lib", "gstreamer-1.0", "libgstx264.dylib"), "w").write("x")
    case(results, "nogpl", "lib/gstreamer-1.0/libgstx264.dylib present", G.nogpl_problems(gpl_engine, "", ff_ok)[0])

    shutil.rmtree(tmp, ignore_errors=True)
    covered = {r["gate"] for r in results}
    missing = [name for name, _ in G.GATES if name not in covered]
    if missing:
        results.append({"gate": "selftest", "result": "FAIL", "detail": "gates with no bad-input case: " + ", ".join(missing),
                        "problems": missing})
    G.report(results, "Gate self-test (each gate must fail on a bad input)")
    import json
    json.dump(results, open(os.path.join(ctx["work"], "gates", "selftest.json"), "w"), indent=2)
    return all(r["result"] == "PASS" for r in results)
