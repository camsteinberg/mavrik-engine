#!/usr/bin/env python3
"""Small build helpers.

  buildinfo.py keys INPUTS                  print GitHub step outputs: cache keys and the engine version
  buildinfo.py write INPUTS WORK ENGINE     write ENGINE/build-info.json, the engine's build record
"""
import hashlib
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def keys(inputs_path):
    doc = json.load(open(inputs_path))
    pins = doc["inputs"]
    target = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    s = os.path.join(REPO, "scripts")
    downloads = digest(doc["inputs"], doc["licence_texts"])
    deps = digest([pins[k] for k in ("gmp", "nettle", "gnutls", "freetype", "sdl2")], target,
                  os.path.join(s, "build-deps.sh"))
    wine = digest(pins["crossover-sources"], pins["gstreamer-runtime"], pins["gstreamer-devel"], deps, target,
                  os.path.join(s, "build-wine.sh"), os.path.join(s, "prepare.sh"), *patches())
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
    config = open(os.path.join(work, "wine-install", ".build", "config.h")).read() if os.path.exists(
        os.path.join(work, "wine-install", ".build", "config.h")) else ""
    run = os.environ.get("GITHUB_RUN_ID")
    info = {
        "name": os.path.basename(engine),
        "wine": wine_version,
        "source": "CodeWeavers' published CrossOver sources (LGPL), not CrossOver",
        "crossover_sources": doc["inputs"]["crossover-sources"]["version"],
        "revision": doc["engine"]["revision"],
        "macos_deployment_target": doc["engine"]["macos_deployment_target"],
        "architecture": "x86_64 Unix side; i386 and x86_64 Windows side",
        "inputs": {k: {"version": v.get("version"), "sha256": v.get("sha256"), "url": v["url"]}
                   for k, v in doc["inputs"].items() if v.get("role") != "tool"},
        "patches": [{"file": os.path.basename(p), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()}
                    for p in patches()],
        "recipe_commit": os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD"),
        "build_run": f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{run}" if run else None,
        "sonames": sorted(l.split(None, 2)[2].strip('"') for l in config.splitlines() if l.startswith("#define SONAME_")),
        "licences": "licences/README.txt",
        "bugs": "https://github.com/camsteinberg/mavrik-engine/issues (never CodeWeavers or WineHQ)",
    }
    json.dump(info, open(os.path.join(engine, "build-info.json"), "w"), indent=2)
    print(json.dumps(info, indent=2))


def main(argv):
    if len(argv) == 3 and argv[1] == "keys":
        keys(argv[2])
    elif len(argv) == 5 and argv[1] == "write":
        write(argv[2], argv[3], argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
