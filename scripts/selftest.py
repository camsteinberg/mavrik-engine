"""Self-test for the gates: each gate is fed a bad input and must fail on it.

Called by `gates.py selftest ENGINE WORK` after the real gates passed. The bad inputs are small
made-up files, or an APFS clone of the engine with one thing broken, in a scratch folder. Each bad
input breaks only the property its gate checks, and every problem the gate reports must be about
that property (the case's `expect` pattern): a gate that failed for another reason would prove
nothing about the check the case names.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import gates as G

# When the self-test started: it stops at the first syspolicyd crash report written since (gates.py,
# syspolicyd_stop), so it starts no more programs that would wait on syspolicyd.
START = None

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
# An ntdll with CrossOver's CW HACK 22144 as CodeWeavers ship it (the link only with WINEDLLPATH set, and
# a hard link first): this revision's lib/wine/x86_64-unix/ntdll.so built from the same patched tree with
# patch 0007 reversed, the same configure line, stripped (strip -x -S). Name it in SELFTEST_OLD_NTDLL;
# without it the dockname rows that need it are not run. Up to revision 6 this was revision 4's ntdll.so
# (00a4da2f...), but patches 0018 to 0032 change ntdll's Unix side, and a revision 7 prefix boot with
# revision 4's hangs (S213).
OLD_NTDLL_SHA256 = "56e09af95401b4a979c9cb6aac685fc09552a76f16812b0e41361612c9cd15f6"


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
    stop, why = G.syspolicyd_stop(START) if START else (False, "")
    if stop:
        raise SystemExit(f"selftest stopped at {gate} ({bad_input}): {why}")
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
    global START
    START = time.time()
    G.syspolicyd_watch()
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
    dxmt = G.dxmt_winemetal_source(ctx)
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

    # fonts: an engine clone whose wine.inf has no FontFiles section; and one whose FontFiles lines lost
    # COPYFLG_NO_OVERWRITE, so wineboot --update must replace the file put in place of a font. (Never an engine without
    # the font files: setupapi then asks for the missing files in a window and Wine waits for an answer.)
    bad = os.path.join(tmp, "no-fontfiles-engine")
    clone(engine, bad)
    inf = os.path.join(bad, "share", "wine", "wine.inf")
    text = open(inf, encoding="utf-8").read()
    os.remove(inf)
    open(inf, "w", encoding="utf-8").write(text.replace("[FontFiles]", "[NoFontFiles]"))
    case(results, "fonts", "an engine clone whose wine.inf has no FontFiles section", G.fonts_check(bad)[0],
         r"wine\.inf has no FontFiles section")
    bad = os.path.join(tmp, "overwriting-fonts-engine")
    clone(engine, bad)
    inf = os.path.join(bad, "share", "wine", "wine.inf")
    text = open(inf, encoding="utf-8").read()
    os.remove(inf)
    open(inf, "w", encoding="utf-8").write(re.sub(r"(?m)^(\w+\.ttf,[\w-]+\.ttf),,0x10$", r"\1,,0", text))
    case(results, "fonts", "an engine clone whose FontFiles lines lost COPYFLG_NO_OVERWRITE", G.fonts_check(bad, timeout=600)[0],
         r"wineboot --update replaced the \S+ that was already in C:\\windows\\Fonts")

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
    bad = os.path.join(tmp, "no-gecko-engine")
    clone(engine, bad)
    shutil.rmtree(os.path.join(bad, "share", "wine", "gecko"))
    case(results, "wine", "an engine clone with Mono but no Gecko", G.wineboot_check(bad, gecko, timeout=600)[0],
         r"Wine Gecko \(x86_64\) started a download prompt")
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

    # dxmt: the engine's DXMT files and build record in a scratch engine, then one thing changed in each copy:
    # winemetal.dll without patch 0001's export (nvngx.dll in its place), winemetal.so naming the work folder,
    # and a build record listing another patch.
    def dxmt_engine(name):
        root = os.path.join(tmp, name)
        for f in ctx["inputs"]["inputs"]["dxmt-source"]["files"]:
            os.makedirs(os.path.dirname(os.path.join(root, "lib", "wine", f)), exist_ok=True)
            clone(os.path.join(engine, "lib", "wine", f), os.path.join(root, "lib", "wine", f))
        shutil.copy(os.path.join(engine, "build-info.json"), os.path.join(root, "build-info.json"))
        return root
    bad = dxmt_engine("dxmt-no-export")
    win = os.path.join(bad, "lib", "wine", "x86_64-windows")
    os.remove(os.path.join(win, "winemetal.dll"))
    shutil.copy(os.path.join(win, "nvngx.dll"), os.path.join(win, "winemetal.dll"))
    case(results, "dxmt", "DXMT's files with another DLL as winemetal.dll (no MetalDrawable_signalEventWhenPresented)",
         G.dxmt_check(bad, ctx)[0], r"winemetal\.dll")
    bad = dxmt_engine("dxmt-buildpath")
    so = os.path.join(bad, "lib", "wine", "x86_64-unix", "winemetal.so")
    data = open(so, "rb").read()
    os.remove(so)
    open(so, "wb").write(data + ctx["work"].encode() + b"/dxmt-src/src/winemetal/unix/winemetal_unix.c\0")
    case(results, "dxmt", "DXMT's files with the work folder's path added to winemetal.so", G.dxmt_check(bad, ctx)[0],
         r"winemetal\.so")
    bad = dxmt_engine("dxmt-patches")
    info = json.load(open(os.path.join(bad, "build-info.json")))
    info["dxmt"]["patches"].append({"file": "0099-not-in-the-recipe.patch", "sha256": "0" * 64})
    json.dump(info, open(os.path.join(bad, "build-info.json"), "w"))
    case(results, "dxmt", "a build record naming a patch the recipe does not have", G.dxmt_check(bad, ctx)[0],
         r"built with patches")

    # d3d11's log checks, through the gate's own probe runner on the real engine (no window, display driver off): a
    # stand-in probe whose checks pass but whose output carries DXMT's presentation timeout line; and one whose output
    # lacks DXMT's ordinary device line, as when DXMT's log goes somewhere the gate does not read.
    for name, lines, expect in (
            ("d3d11-timeout", [G.DXMT_LOG_LINE + " 0xb100", "warn:  Frame 7 " + G.PRESENT_TIMEOUT + " 100ms"],
             re.escape(G.PRESENT_TIMEOUT)),
            ("d3d11-nolog", ["info:  nothing from DXMT here"], re.escape(G.DXMT_LOG_LINE))):
        exe = os.path.join(tmp, name, name + ".exe")
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        body = "".join('    puts("%s"); fflush(stdout);\n' % l.replace('"', '\\"') for l in lines)
        open(exe + ".c", "w").write("#include <stdio.h>\nint main(void)\n{\n" + body
                                    + '    puts("check\\tstand-in\\tok\\tran"); puts("done\\t0"); return 0;\n}\n')
        subprocess.run([G.PE_COMPILERS["64"], "-O1", "-s", "-o", exe, exe + ".c"], check=True)
        problems = G.probe_check(engine, [(exe, [])], forbid=[G.PRESENT_TIMEOUT], require=[G.DXMT_LOG_LINE])[0]
        case(results, "d3d11", f"a stand-in probe printing {lines[-1]!r}", problems, expect)

    # d3d11: an engine clone without DXMT's Unix side (winemetal.so), where Direct3D 11 cannot reach Metal.
    if G.metal_device(ctx["work"]):
        bad = os.path.join(tmp, "no-winemetal-engine")
        clone(engine, bad)
        os.remove(os.path.join(bad, "lib", "wine", "x86_64-unix", "winemetal.so"))
        case(results, "d3d11", "an engine clone without lib/wine/x86_64-unix/winemetal.so", G.d3d11_check(bad, ctx)[0],
             r"d3d11probe64\.exe: (device|present|vsync|readback) failed|d3d11probe64\.exe did not run to the end|winemetal\.so")
    else:
        skipped(results, "d3d11", "an engine clone without winemetal.so", "this machine has no Metal device")

    # playback: an engine clone without GStreamer's FFmpeg plugin, so no H.264 or AAC decoder.
    bad = os.path.join(tmp, "no-libav-engine")
    clone(engine, bad)
    os.remove(os.path.join(bad, "lib", "gstreamer-1.0", "libgstlibav.dylib"))
    case(results, "playback", "an engine clone without lib/gstreamer-1.0/libgstlibav.dylib", G.playback_check(bad, ctx)[0],
         r"mediaprobe(32|64)\.exe: (mf|wm)-(video|audio) failed|libgstlibav\.dylib")

    # steamredirect: the bridge turned off with Valve's own switch, so the steamclient DLL's export stays its own.
    case(results, "steamredirect", "the bridge turned off with PROTON_DISABLE_LSTEAMCLIENT=1",
         G.steamredirect_check(engine, ctx, {"PROTON_DISABLE_LSTEAMCLIENT": "1"})[0],
         r"steamprobe(32|64)\.exe: redirect failed")

    # dockname: an engine clone whose Mac driver cannot find LaunchServices' naming call (the name it looks
    # up is changed in winemac.so, which is then signed again), with the title no link can carry, so the
    # Dock keeps "wine" (patch 0007's link names the process for every other title; the call is its
    # fallback). The probe's windows must still appear: the driver goes on quietly without the call.
    if G.login_session() == "Aqua":
        bad = os.path.join(tmp, "no-naming-call-engine")
        clone(engine, bad)
        winemac = os.path.join(bad, "lib", "wine", "x86_64-unix", "winemac.so")
        data = open(winemac, "rb").read()
        name = b"_LSSetApplicationInformationItem"
        assert data.count(name) == 1, f"winemac.so names {name.decode()} {data.count(name)} times"
        os.remove(winemac)  # a new file, not the clone's shared blocks
        open(winemac, "wb").write(data.replace(name, b"_LSSetApplicationInformationXxxx"))
        subprocess.run(["codesign", "-s", "-", "-f", winemac], check=True, capture_output=True)
        case(results, "dockname", "an engine clone whose winemac.so cannot find _LSSetApplicationInformationItem",
             G.dockname_check(bad, ctx, cases=[G.DOCK_FALLBACK])[0],
             r"dockprobe(32|64)\.exe: the Dock shows 'wine', not '\.\.'")

        # dockname: titles past the loader's 32-byte name slot once escaped, one of '&' (5 bytes each
        # escaped) and one of CJK characters (3 bytes each). The Dock must show each cut between whole
        # escapes or whole characters; a cut inside one makes Core Foundation reject the loader's
        # Info.plist, and the Dock then shows "wine", which these rows do not accept.
        # The window server shows the CJK one cut too (patch 0007's 31 bytes), to the same characters.
        long_titles = {"&&&&&&&": "&&&&&&", "名前" * 5 + "名": "名前" * 5}
        problems = G.dockname_check(engine, ctx, cases=list(long_titles))[0]
        for title, shown in long_titles.items():
            case(results, "dockname", f"the title '{title}', past the 32-byte name slot once escaped",
                 [p for p in problems if p.startswith(f"'{title}': ") or not p.startswith("'")],
                 r"dockprobe(32|64)\.exe: the (Dock|window server) shows " + re.escape(f"'{shown}', not '{title}'"))

        # dockname, the window server and the executable: an engine clone with the ntdll.so without patch 0007
        # (CW HACK 22144 as shipped, see OLD_NTDLL_SHA256). Without WINEDLLPATH no link is made, so the
        # window server must show "wine" while LaunchServices (patch 0006) still shows the title. With
        # WINEDLLPATH set, the hack starts each program through a hard link in the user's temp folder,
        # so the executable must be reported outside the engine: only those problems are kept, because
        # the hack also names each program after its file there.
        old = os.environ.get("SELFTEST_OLD_NTDLL")
        if old:
            if G.out(["shasum", "-a", "256", old]).stdout.split()[:1] != [OLD_NTDLL_SHA256]:
                raise SystemExit(f"selftest setup: SELFTEST_OLD_NTDLL {old} is not this revision's ntdll.so without patch 0007")
            bad = os.path.join(tmp, "old-ntdll-engine")
            clone(engine, bad)
            ntdll = os.path.join(bad, "lib", "wine", "x86_64-unix", "ntdll.so")
            os.remove(ntdll)
            shutil.copy2(old, ntdll)
            case(results, "dockname", "an engine clone with an ntdll that makes the link only with WINEDLLPATH set",
                 G.dockname_check(bad, ctx, cases=["Gate Dock Name"])[0],
                 r"dockprobe(32|64)\.exe: the window server shows 'wine', not 'Gate Dock Name'")
            problems = G.dockname_check(bad, ctx, cases=["Gate Dock Name"],
                                        extra_env={"WINEDLLPATH": os.path.join(bad, "lib", "wine")})[0]
            case(results, "dockname", "the same clone with WINEDLLPATH set, so each program starts through a hard link",
                 [p for p in problems if p.endswith(", outside the engine")],
                 r"dockprobe(32|64)\.exe: started from \S*/winetemp-[^/]+/[^/]+, outside the engine")
        else:
            skipped(results, "dockname", "an ntdll with CrossOver's link condition, and one with its hard link",
                    "SELFTEST_OLD_NTDLL is not set")
    else:
        skipped(results, "dockname", "an engine clone without the naming call, titles past the name slot, an ntdll "
                "with CrossOver's link condition, and one with its hard link", "not in a login (Aqua) session")

    # The engine clones Wine ran from go only now: macOS's syspolicyd checks each new program while it
    # runs, and crashes when the file is gone before it gets to it (S213; it crashed on such files from
    # mavrik's own tests 17 times in a row, and the Mac hung while launchd held it back).
    shutil.rmtree(tmp, ignore_errors=True)
    G.remove_deferred()
    covered = {r["gate"] for r in results}
    missing = [name for name, _ in G.GATES if name not in covered]
    if missing:
        results.append({"gate": "selftest", "result": "FAIL", "detail": "gates with no bad-input case: " + ", ".join(missing),
                        "problems": missing})
    G.report(results, "Gate self-test (each gate must fail on a bad input, for that gate's reason)")
    json.dump(results, open(os.path.join(ctx["work"], "gates", "selftest.json"), "w"), indent=2)
    return all(r["result"] in ("PASS", "SKIP") for r in results)
