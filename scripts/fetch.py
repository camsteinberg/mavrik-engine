#!/usr/bin/env python3
"""Download every input named in inputs.json and check its size and SHA-256.

  fetch.py fetch INPUTS DEST [--release] [--from DIR] [--via curl|gh]
  fetch.py check-pins INPUTS               fail if any input has no size or no sha256

DEST gets one file per input and DEST/paths.json (input -> file). A file already in DEST that
matches every value pinned for it is reused.

  --from DIR   a folder of files downloaded by hand, each named as the last part of its URL. A file
               found there is taken (cloned, not downloaded) and checked exactly like a download.
  --via curl   download with curl (the default, as on GitHub's runner).
  --via gh     download GitHub release assets and raw GitHub files with the GitHub CLI; any other
               input must be in the --from folder. For a Mac where curl is not to be used.

An input with no size or sha256 is refused in a release build. In a test build it is used, its
values are printed and written to DEST/learned-pins.json so they can be pinned, and the build goes
on with a warning. Every input is tried before the script fails, so one run names every input that
is missing or does not match its pin.
"""
import hashlib
import json
import os
import re
import shutil
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
    """True when the file agrees with every value pinned for it (and at least one is pinned)."""
    if not os.path.isfile(path) or not (entry.get("size") or entry.get("sha256")):
        return False
    if entry.get("size") and os.path.getsize(path) != entry["size"]:
        return False
    return not entry.get("sha256") or sha256_of(path) == entry["sha256"]


def via_curl(url, part):
    subprocess.run(["curl", "-fL", "--retry", "5", "--retry-all-errors", "--retry-delay", "5",
                    "--connect-timeout", "30", "-sS", "-A", "mavrik-engine-build", "-o", part, url], check=True)


RELEASE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/]+)$")
RAW = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$")


def via_gh(url, part):
    m = RELEASE.match(url)
    if m:
        owner, repo, tag, name = m.groups()
        folder = part + ".d"
        shutil.rmtree(folder, ignore_errors=True)
        subprocess.run(["gh", "release", "download", tag, "-R", f"{owner}/{repo}", "-p", name, "-D", folder],
                       check=True)
        os.replace(os.path.join(folder, name), part)
        shutil.rmtree(folder)
        return
    m = RAW.match(url)
    if m:
        owner, repo, ref, path = m.groups()
        with open(part, "wb") as f:
            subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                            f"/repos/{owner}/{repo}/contents/{path}?ref={ref}"], stdout=f, check=True)
        return
    raise LookupError("not on GitHub, and not in the --from folder")


def obtain(url, path, source, via):
    """Puts the input at path: from the hand-downloaded folder if it is there, else downloads it."""
    part = path + ".part"
    if source:
        hand = os.path.join(source, os.path.basename(url))
        if os.path.isfile(hand):
            print(f"  from {hand}", flush=True)
            if subprocess.run(["cp", "-c", hand, part], capture_output=True).returncode:
                shutil.copyfile(hand, part)
            os.replace(part, path)
            return
    if via == "gh":
        print(f"  downloading {url} with gh", flush=True)
        via_gh(url, part)
    else:
        print(f"  downloading {url}", flush=True)
        via_curl(url, part)
    os.replace(part, path)


def fetch(inputs_path, dest, release, source, via):
    doc = json.load(open(inputs_path))
    missing = unpinned(doc)
    if release and missing:
        sys.exit("refusing a release build: these inputs have no pinned size or sha256: " + ", ".join(missing))
    os.makedirs(dest, exist_ok=True)
    paths, learned, failed, absent = {}, {}, [], []
    for section, key, entry in entries(doc):
        name = f"{key}--{os.path.basename(entry['url'])}"
        path = os.path.join(dest, name)
        if not matches(path, entry):
            print(f"{key}:", flush=True)
            try:
                obtain(entry["url"], path, source, via)
            except (LookupError, subprocess.CalledProcessError) as e:
                absent.append(f"{key}: {entry['url']} ({e})")
                continue
        size, digest = os.path.getsize(path), sha256_of(path)
        bad = []
        if entry.get("size") and size != entry["size"]:
            bad.append(f"{key}: size {size}, pinned {entry['size']}")
        if entry.get("sha256") and digest != entry["sha256"]:
            bad.append(f"{key}: sha256 {digest}, pinned {entry['sha256']}")
        if bad:
            failed += bad
            continue
        if not entry.get("size") or not entry.get("sha256"):
            learned[key] = {"size": size, "sha256": digest}
            print(f"::warning::{key} is not fully pinned. Pin it: \"size\": {size}, \"sha256\": \"{digest}\"")
        else:
            print(f"ok {key}: {size} bytes, sha256 {digest}")
        paths[key] = os.path.abspath(path)
    json.dump(paths, open(os.path.join(dest, "paths.json"), "w"), indent=2)
    json.dump(learned, open(os.path.join(dest, "learned-pins.json"), "w"), indent=2)
    print(f"{len(paths)} inputs checked, {len(learned)} not fully pinned")
    for line in absent:
        print("::error::missing " + line)
    for line in failed:
        print("::error::" + line)
    if absent or failed:
        sys.exit(f"{len(absent)} inputs missing and {len(failed)} values not matching their pins")


def main(argv):
    if len(argv) >= 3 and argv[1] == "check-pins":
        missing = unpinned(json.load(open(argv[2])))
        if missing:
            sys.exit("not pinned: " + ", ".join(missing))
        print("every input is pinned")
        return
    if len(argv) >= 4 and argv[1] == "fetch":
        opts = argv[4:]

        def value(flag, default=None):
            if flag not in opts:
                return default
            i = opts.index(flag)
            if i + 1 >= len(opts):
                sys.exit(f"{flag} needs a value")
            return opts[i + 1]

        via = value("--via", "curl")
        if via not in ("curl", "gh"):
            sys.exit("--via is curl or gh")
        source = value("--from")
        if source and not os.path.isdir(source):
            sys.exit(f"--from {source}: no such folder")
        fetch(argv[2], argv[3], "--release" in opts, source and os.path.abspath(source), via)
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
