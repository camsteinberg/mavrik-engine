#!/usr/bin/env python3
"""Small build helpers.

  buildinfo.py keys INPUTS                  print the cache keys (also build.sh's stamps) and the engine version
  buildinfo.py toolchain                    print the toolchain this machine builds with, as JSON
  buildinfo.py write INPUTS WORK ENGINE     write ENGINE/build-info.json, the engine's build record

The keys cover the pinned inputs, the build scripts and patches, and the toolchain itself (Xcode,
its SDK and clang, mingw-w64 gcc, bison, flex, CMake): an engine built by another compiler or
against another SDK is another engine, so it never comes from a cache made by a different one.
Run them with the Xcode toolchain.sh selects (DEVELOPER_DIR).
"""
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# What the engine's folders hold, for a launcher that starts it.
LAYOUT = {
    "wine": "bin/wine",
    "wineserver": "bin/wineserver",
    "loader": "lib/wine/x86_64-unix/wine",
    "unix_libraries": "lib",
    "gstreamer_plugins": "lib/gstreamer-1.0",
    "bundle_identifier": "org.mavrik.engine",
}


def digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, str) and os.path.isfile(p):
            h.update(open(p, "rb").read())
        else:
            h.update(json.dumps(p, sort_keys=True).encode())
    return h.hexdigest()[:20]


def patches():
    d = os.path.join(REPO, "patches")
    return sorted(os.path.join(d, p) for p in os.listdir(d) if p.endswith(".patch"))


def first_line(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [l.strip() for l in (r.stdout or r.stderr).splitlines() if l.strip()]
    return lines[0] if r.returncode == 0 and lines else None


def mingw_version():
    try:
        r = subprocess.run(["x86_64-w64-mingw32-gcc", "-dM", "-E", "-x", "c", "-"], input="#include <_mingw.h>\n",
                           capture_output=True, text=True, timeout=60)
    except OSError:
        return None
    v = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ("__MINGW64_VERSION_MAJOR", "__MINGW64_VERSION_MINOR", "__MINGW64_VERSION_BUGFIX"):
            v[parts[1]] = parts[2]
    if "__MINGW64_VERSION_MAJOR" not in v:
        return None
    return ".".join(v.get(k, "0") for k in ("__MINGW64_VERSION_MAJOR", "__MINGW64_VERSION_MINOR", "__MINGW64_VERSION_BUGFIX"))


def toolchain():
    """The tools that shape the engine's files, as this machine has them (DEVELOPER_DIR respected)."""
    xcode = subprocess.run(["xcodebuild", "-version"], capture_output=True, text=True).stdout.split()
    return {
        "xcode": " ".join(xcode) or None,
        "macos_sdk": first_line(["xcrun", "--show-sdk-version"]),
        "clang": first_line(["clang", "--version"]),
        "x86_64-w64-mingw32-gcc": first_line(["x86_64-w64-mingw32-gcc", "--version"]),
        "i686-w64-mingw32-gcc": first_line(["i686-w64-mingw32-gcc", "--version"]),
        "mingw-w64": mingw_version(),
        "bison": first_line(["bison", "--version"]),
        "flex": first_line(["flex", "--version"]),
        "cmake": first_line(["cmake", "--version"]),
    }


def keys(inputs_path):
    doc = json.load(open(inputs_path))
    pins = doc["inputs"]
    target = doc["engine"]["macos_deployment_target"]
    s = os.path.join(REPO, "scripts")
    tc = toolchain()
    missing = [k for k, v in tc.items() if v is None]
    if missing:
        sys.exit("toolchain: cannot read " + ", ".join(missing))
    unix_tools = {k: tc[k] for k in ("xcode", "macos_sdk", "clang", "cmake")}
    pe_tools = {k: tc[k] for k in ("x86_64-w64-mingw32-gcc", "i686-w64-mingw32-gcc", "mingw-w64", "bison", "flex")}
    downloads = digest(doc["inputs"], doc["licence_texts"])
    deps = digest([pins[k] for k in ("gmp", "nettle", "gnutls", "freetype", "sdl2")], target, unix_tools,
                  os.path.join(s, "build-deps.sh"))
    wine = digest(pins["crossover-sources"], pins["gstreamer-runtime"], pins["gstreamer-devel"], deps, target,
                  unix_tools, pe_tools, os.path.join(s, "build-wine.sh"), os.path.join(s, "prepare.sh"), *patches())
    cx = pins["crossover-sources"]["version"]
    version = f"cx{cx}-r{doc['engine']['revision']}"
    print(f"downloads=downloads-{downloads}")
    print(f"deps=deps-{deps}")
    print(f"wine=wine-{wine}")
    print(f"version={version}")


def write(inputs_path, work, engine):
    doc = json.load(open(inputs_path))
    def git(*a):
        return subprocess.run(["git", "-C", REPO] + list(a), capture_output=True, text=True).stdout.strip()
    wine_version = open(os.path.join(work, "wine-src", "VERSION")).read().strip()
    config_h = os.path.join(work, "wine-install", ".build", "config.h")
    config = open(config_h).read() if os.path.exists(config_h) else ""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from assemble import NOT_CARRIED
    sonames = {}
    for line in config.splitlines():
        if line.startswith("#define SONAME_"):
            _, define, value = line.split(None, 2)
            sonames[define] = value.strip('"')
    run = os.environ.get("GITHUB_RUN_ID")
    built_with = os.path.join(work, "wine-install", ".build", "toolchain.json")
    info = {
        "name": os.path.basename(engine),
        "wine": wine_version,
        "source": "CodeWeavers' published CrossOver sources (LGPL), not CrossOver",
        "crossover_sources": doc["inputs"]["crossover-sources"]["version"],
        "revision": doc["engine"]["revision"],
        "macos_deployment_target": doc["engine"]["macos_deployment_target"],
        "architecture": "x86_64 Unix side; i386 and x86_64 Windows side",
        "layout": LAYOUT,
        "inputs": {k: {"version": v.get("version"), "sha256": v.get("sha256"), "url": v["url"]}
                   for k, v in doc["inputs"].items() if v.get("role") != "tool"},
        "patches": [{"file": os.path.basename(p), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
                    for p in patches()],
        # What Wine was compiled with (recorded by build-wine.sh), and what assembled the engine.
        "toolchain": json.load(open(built_with)) if os.path.exists(built_with) else None,
        "assembled_with": toolchain(),
        "recipe_commit": os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD"),
        "build_run": f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{run}" if run else None,
        # The libraries Wine opens by file name, all carried in lib/; and those configure names
        # that the engine leaves out on purpose (Wine opens them only if the Mac has them).
        "sonames": sorted({v for k, v in sonames.items() if k not in NOT_CARRIED}),
        "sonames_not_carried": sorted({v for k, v in sonames.items() if k in NOT_CARRIED}),
        "licences": "licences/README.txt",
        "bugs": "https://github.com/camsteinberg/mavrik-engine/issues (never CodeWeavers or WineHQ)",
    }
    json.dump(info, open(os.path.join(engine, "build-info.json"), "w"), indent=2)
    print(json.dumps(info, indent=2))


def main(argv):
    if len(argv) == 3 and argv[1] == "keys":
        keys(argv[2])
    elif len(argv) == 2 and argv[1] == "toolchain":
        print(json.dumps(toolchain(), indent=2))
    elif len(argv) == 5 and argv[1] == "write":
        write(argv[2], argv[3], argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
