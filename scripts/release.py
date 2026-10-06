#!/usr/bin/env python3
"""Release helpers.

  release.py collect INPUTS WORK DEST   copy the corresponding source of every LGPL or MPL part into DEST;
                                        refuse if any part's source is not pinned in inputs.json
  release.py notes INPUTS NAME RUN_ID   print the release notes

A release carries the engine, its checksum, and the source of every part whose licence asks for
it: Wine (the CrossOver source archive and this repository's patches), GnuTLS, Nettle, GMP, Wine
Mono, Wine Gecko, DXMT (its winemetal.dll carries Wine's start-up code), and the LGPL parts of the
media component: the exact tarballs GStreamer's build recipes (cerbero 1.28.6) built them from, and
cerbero itself, which holds the patches it applied. A part whose source is not pinned (an input with
role "source", or an entry in "release_sources") stops the release.
"""
import json
import os
import shutil
import sys
import tarfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEEDS_SOURCE = ["wine", "gmp", "nettle", "gnutls", "wine-mono", "wine-gecko", "dxmt",
                "media:gstreamer", "media:glib", "media:ffmpeg", "media:proxy-libintl", "media:mpg123",
                "media:cerbero"]


def sources(doc):
    """{component: [(key, entry)]} for every pinned source."""
    have = {}
    for key, entry in doc["inputs"].items():
        if entry.get("role") == "source":
            have.setdefault(entry["component"], []).append((key, entry))
    for key, entry in doc.get("release_sources", {}).items():
        have.setdefault(entry["component"], []).append((key, entry))
    return have


def collect(inputs_path, work, dest):
    doc = json.load(open(inputs_path))
    paths = json.load(open(os.path.join(work, "downloads", "paths.json")))
    have = sources(doc)
    missing = [c for c in NEEDS_SOURCE if c not in have]
    if missing:
        sys.exit("refusing to publish: no pinned source for " + ", ".join(missing)
                 + ". Add each to release_sources in inputs.json first.")
    unpinned = [k for c in NEEDS_SOURCE for k, e in have[c] if not e.get("size") or not e.get("sha256")]
    absent = [k for c in NEEDS_SOURCE for k, _ in have[c] if k not in paths]
    if unpinned or absent:
        sys.exit("refusing to publish: " + "; ".join(
            ([f"not pinned: {', '.join(unpinned)}"] if unpinned else []) +
            ([f"not downloaded: {', '.join(absent)}"] if absent else [])))
    os.makedirs(dest, exist_ok=True)
    for comp in NEEDS_SOURCE:
        for key, entry in have[comp]:
            name = entry.get("file") or os.path.basename(entry["url"])
            shutil.copy(paths[key], os.path.join(dest, name))
    with tarfile.open(os.path.join(dest, "mavrik-engine-recipe.tar.gz"), "w:gz") as t:
        for name in ("README.md", "NOTICE.md", "LICENSE", "inputs.json", "patches", "scripts", "tools", ".github"):
            t.add(os.path.join(REPO, name), arcname=name,
                  filter=lambda i: None if "__pycache__" in i.name else i)
    print("\n".join(sorted(os.listdir(dest))))


def notes(inputs_path, name, run_id):
    doc = json.load(open(inputs_path))
    cx = doc["inputs"]["crossover-sources"]["version"]
    print(f"""{name}

mavrik's Wine engine, built from CodeWeavers' published CrossOver {cx} sources (LGPL) with the patches in
patches/. This is not CrossOver. Report bugs in this repository, never to CodeWeavers or WineHQ.

This is a prerelease for testing. It is checked by the build's gates (see the .gates.json file) and
is not yet a full release.

The engine's own licences/ folder lists every part and its licence. The source of every LGPL and MPL
part is attached to this release.

Built by run {run_id}. Check the download with the .sha256 file.""")


def main(argv):
    if len(argv) == 5 and argv[1] == "collect":
        collect(argv[2], argv[3], argv[4])
    elif len(argv) == 5 and argv[1] == "notes":
        notes(argv[2], argv[3], argv[4])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
