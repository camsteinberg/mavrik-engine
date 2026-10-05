#!/usr/bin/env python3
"""Download every input named in inputs.json and check its size and SHA-256.

  fetch.py fetch INPUTS DEST [--release]   download into DEST, check, write DEST/paths.json
  fetch.py check-pins INPUTS               fail if any input has no size or no sha256

A file already in DEST that matches its pin is reused. An input with no size or sha256 is
refused in a release build. In a test build it is downloaded, its values are printed so they
can be pinned, and the build goes on with a warning.
"""
import hashlib
import json
import os
import subprocess
import sys

SECTIONS = ("inputs", "licence_texts")


def entries(doc):
    for section in SECTIONS:
        for key, entry in doc.get(section, {}).items():
            yield section, key, entry


def unpinned(doc):
    return [f"{s}.{k}" for s, k, e in entries(doc) if not e.get("sha256") or not e.get("size")]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def matches(path, entry):
    if not os.path.isfile(path):
        return False
    if entry.get("size") and os.path.getsize(path) != entry["size"]:
        return False
    if entry.get("sha256") and sha256_of(path) != entry["sha256"]:
        return False
    return bool(entry.get("size") and entry.get("sha256"))


def download(url, path):
    part = path + ".part"
    cmd = ["curl", "-fL", "--retry", "5", "--retry-all-errors", "--retry-delay", "5",
           "--connect-timeout", "30", "-sS", "-A", "mavrik-engine-build", "-o", part, url]
    subprocess.run(cmd, check=True)
    os.replace(part, path)


def fetch(inputs_path, dest, release):
    doc = json.load(open(inputs_path))
    missing = unpinned(doc)
    if release and missing:
        sys.exit("refusing a release build: these inputs have no pinned size or sha256: " + ", ".join(missing))
    os.makedirs(dest, exist_ok=True)
    paths, learned, failed = {}, {}, []
    for section, key, entry in entries(doc):
        name = f"{key}--{os.path.basename(entry['url'])}"
        path = os.path.join(dest, name)
        if not matches(path, entry):
            print(f"downloading {key}: {entry['url']}", flush=True)
            download(entry["url"], path)
        size, digest = os.path.getsize(path), sha256_of(path)
        if entry.get("size") and size != entry["size"]:
            failed.append(f"{key}: size {size}, pinned {entry['size']}")
        if entry.get("sha256") and digest != entry["sha256"]:
            failed.append(f"{key}: sha256 {digest}, pinned {entry['sha256']}")
        if not entry.get("size") or not entry.get("sha256"):
            learned[key] = {"size": size, "sha256": digest}
            print(f"::warning::{key} is not fully pinned. Pin it: \"size\": {size}, \"sha256\": \"{digest}\"")
        else:
            print(f"ok {key}: {size} bytes, sha256 {digest}")
        paths[key] = os.path.abspath(path)
    if failed:
        for line in failed:
            print("::error::" + line)
        sys.exit("an input does not match its pin")
    json.dump(paths, open(os.path.join(dest, "paths.json"), "w"), indent=2)
    json.dump(learned, open(os.path.join(dest, "learned-pins.json"), "w"), indent=2)
    print(f"{len(paths)} inputs checked, {len(learned)} not fully pinned")


def main(argv):
    if len(argv) >= 3 and argv[1] == "check-pins":
        missing = unpinned(json.load(open(argv[2])))
        if missing:
            sys.exit("not pinned: " + ", ".join(missing))
        print("every input is pinned")
        return
    if len(argv) >= 4 and argv[1] == "fetch":
        fetch(argv[2], argv[3], "--release" in argv[4:])
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
