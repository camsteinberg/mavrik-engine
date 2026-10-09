#!/usr/bin/env python3
"""Proton's source for the Steam bridge: unpack the pinned folders and check what was unpacked.

  proton.py unpack INPUTS TARBALL DEST   unpack the members bridge/inputs.json names into DEST (which
                                         must not exist) and stop unless their tree digest is pinned
  proton.py digest DIR MEMBER...         print the tree digest of DIR's members

GitHub makes a commit's tarball when asked, and its compression can change from one download to the
next (NotProton's lsteamclient/fetch.sh pins the unpacked tree for the same reason). So the tarball's
size and sha256 in inputs.json name one download, and the tree digest pins what is built: for every
file under the members, in sorted path order, the sha256 of its path and then of its bytes, hashed
together. The tarball is untrusted data until it matches: unpack refuses absolute paths, '..', links
and anything that is not a plain file or folder.
"""
import hashlib
import json
import os
import shutil
import sys
import tarfile


def files_under(root, members):
    found = []
    for member in members:
        top = os.path.join(root, member)
        if os.path.isfile(top):
            found.append(member)
            continue
        if not os.path.isdir(top):
            sys.exit(f"{member}: not in {root}")
        for dirpath, dirnames, filenames in os.walk(top):
            for name in dirnames + filenames:
                p = os.path.join(dirpath, name)
                if os.path.islink(p):
                    sys.exit(f"{os.path.relpath(p, root)} is a link")
            found += [os.path.relpath(os.path.join(dirpath, n), root) for n in filenames]
    return sorted(found)


def digest(root, members):
    h = hashlib.sha256()
    names = files_under(root, members)
    for rel in names:
        h.update(hashlib.sha256(rel.encode()).digest())
        h.update(hashlib.sha256(open(os.path.join(root, rel), "rb").read()).digest())
    return h.hexdigest(), len(names)


def unpack(inputs_path, tarball, dest):
    pin = json.load(open(inputs_path))["inputs"]["proton-source"]
    members = pin["members"]
    if os.path.exists(dest):
        sys.exit(f"{dest} already exists")
    tmp = dest + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    with tarfile.open(tarball) as t:
        chosen = []
        for m in t.getmembers():
            parts = m.name.split("/")
            if m.name.startswith("/") or ".." in parts:
                sys.exit(f"unsafe entry in the tarball: {m.name}")
            # GitHub's tarballs hold one folder, <owner>-<repo>-<commit>; the members are inside it.
            if len(parts) < 2 or not any(parts[1] == mem.split("/")[0] for mem in members):
                continue
            if not (m.isfile() or m.isdir()):
                sys.exit(f"not a plain file or folder ({m.type!r}): {m.name}")
            m.name = "/".join(parts[1:])
            m.mode &= 0o755
            chosen.append(m)
        t.extractall(tmp, members=chosen, filter="data")
    value, count = digest(tmp, members)
    if value != pin["tree_sha256"]:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(f"Proton {pin['commit']}: tree digest {value} over {count} files, pinned {pin['tree_sha256']} "
                 f"over {pin['tree_files']}")
    if count != pin["tree_files"]:
        sys.exit(f"Proton {pin['commit']}: {count} files, pinned {pin['tree_files']}")
    os.replace(tmp, dest)
    print(f"Proton {pin['commit'][:7]}: {', '.join(members)} unpacked, {count} files, tree digest {value}")


def main(argv):
    if len(argv) == 5 and argv[1] == "unpack":
        unpack(argv[2], argv[3], argv[4])
    elif len(argv) >= 4 and argv[1] == "digest":
        value, count = digest(argv[2], argv[3:])
        print(f"{value} {count}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
