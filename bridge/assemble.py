#!/usr/bin/env python3
"""Turn the bridge's build into its own folder, as scripts/assemble.py does for the engine.

  bridge/assemble.py WORK

Reads WORK/bridge/install (bridge/build.sh) and makes WORK/bridge/out/<name>, where <name> is
mavrik-steam-bridge-proton-<commit>-r<revision>:
  lib/wine/i386-windows/{lsteamclient.dll,steam.exe}
  lib/wine/x86_64-windows/{lsteamclient.dll,steam.exe}
  lib/wine/x86_64-unix/lsteamclient.so
  NOTICE.txt, build-info.json, licences/ (scripts/licences.py bridge)
The files sit where the engine's own lib/wine has its modules, so a program that starts the engine
adds them to the engine's lib/wine, the one tree Proton and NotProton ship them in. The Windows files
are stripped of debug data and the Unix half with strip -x -S, like the engine's. Nothing here signs
the Unix half: Wine's linker leaves it unsigned, and the unsigned gate checks it stays so (NotProton:
"wine builtins fail to load once codesigned"). Writes the name to WORK/bridge/out/name.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["lib/wine/i386-windows/lsteamclient.dll", "lib/wine/x86_64-windows/lsteamclient.dll",
         "lib/wine/x86_64-unix/lsteamclient.so", "lib/wine/i386-windows/steam.exe",
         "lib/wine/x86_64-windows/steam.exe"]
STRIP = {"i386-windows": ["i686-w64-mingw32-strip", "--strip-debug"],
         "x86_64-windows": ["x86_64-w64-mingw32-strip", "--strip-debug"], "x86_64-unix": ["strip", "-x", "-S"]}
NOTICE = """mavrik's Steam bridge: {name}

Built by mavrik from Valve's lsteamclient and steam_helper sources in Proton
(https://github.com/ValveSoftware/Proton, commit {commit}), with mavrik's changes for macOS
(bridge/patches/ in https://github.com/camsteinberg/mavrik-engine).

Not made, endorsed or supported by Valve. Steam and Proton are trademarks of Valve Corporation.

lsteamclient is under Valve's Steamworks SDK licence and steam.exe under BSD-3-Clause; both carry Wine's
start-up code under the LGPL. licences/ holds every text. It is used with mavrik's engine, whose loader
(its patch 0004, Valve's) hands a game's Steam calls to lsteamclient, which passes them to the Steam
app on this Mac.
"""


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    work = os.path.abspath(argv[1])
    doc = json.load(open(os.path.join(REPO, "bridge", "inputs.json")))
    pin, info = doc["inputs"]["proton-source"], doc["bridge"]
    name = f"{info['name']}-proton-{pin['commit'][:7]}-r{info['revision']}"
    src = os.path.join(work, "bridge", "install")
    out = os.path.join(work, "bridge", "out", name)
    if os.path.exists(out):
        shutil.rmtree(out)
    for rel in FILES:
        os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(src, rel), os.path.join(out, rel))
        os.chmod(os.path.join(out, rel), 0o755 if rel.endswith(".so") else 0o644)
        before = os.path.getsize(os.path.join(out, rel))
        subprocess.run(STRIP[rel.split("/")[2]] + [os.path.join(out, rel)], check=True, capture_output=True)
        print(f"{rel}: {before} -> {os.path.getsize(os.path.join(out, rel))} bytes")
    open(os.path.join(out, "NOTICE.txt"), "w").write(NOTICE.format(name=name, commit=pin["commit"]))

    def git(*a):
        return subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True).stdout.strip()
    engine_name = open(os.path.join(work, "out", "name")).read().strip()
    engine_info = json.load(open(os.path.join(work, "out", engine_name, "build-info.json")))
    patches = sorted(p for p in os.listdir(os.path.join(REPO, "bridge", "patches")) if p.endswith(".patch"))
    record = {
        "name": name,
        "revision": info["revision"],
        "source": "Valve's lsteamclient and steam_helper from Proton, with mavrik's patches. Not made by Valve.",
        "proton": {"commit": pin["commit"], "version": pin["version"], "url": pin["url"],
                   "tarball_sha256": pin.get("sha256"), "tree_sha256": pin["tree_sha256"], "members": pin["members"]},
        "patches": [{"file": p, "sha256": sha256(os.path.join(REPO, "bridge", "patches", p))} for p in patches],
        # The engine it was built against (the same Wine tree and configuration) and gated with.
        "engine": {"name": engine_name, "revision": engine_info.get("revision"),
                   "recipe_commit": engine_info.get("recipe_commit")},
        "files": {rel: {"size": os.path.getsize(os.path.join(out, rel)), "sha256": sha256(os.path.join(out, rel))}
                  for rel in FILES},
        "layout": "add lib/wine/* to the engine's lib/wine (the engine's own folders)",
        "toolchain": json.load(open(os.path.join(src, ".build", "toolchain.json"))),
        "recipe_commit": os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD"),
        "licences": "licences/README.txt",
    }
    json.dump(record, open(os.path.join(out, "build-info.json"), "w"), indent=2)
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "licences.py"), "bridge", work, out, REPO], check=True)
    open(os.path.join(work, "bridge", "out", "name"), "w").write(name + "\n")
    print(f"bridge: {out}")


if __name__ == "__main__":
    main(sys.argv)
