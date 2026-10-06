#!/usr/bin/env python3
"""The packed engine holds exactly the gated engine folder, and nothing about the machine that packed it.

  tarcheck.py ARCHIVE.tar.xz FOLDER

Reads the archive without extracting it and compares every entry with FOLDER (type, size, permission
bits). It fails on: an absolute or '..' path, an entry outside the one top-level folder, a link or
any other entry that is not a plain file or folder, an owner other than root:wheel, an extended
attribute, ACL or Mac metadata in an entry's headers (com.apple.provenance and the like), and an
AppleDouble ('._') entry.
"""
import os
import sys
import tarfile

MACHINE_HEADERS = ("LIBARCHIVE.xattr.", "SCHILY.xattr.", "SCHILY.acl.", "SCHILY.fflags", "LIBARCHIVE.creationtime")


def describe(path):
    st = os.lstat(path)
    if os.path.islink(path):
        return ("link", 0, 0)
    if os.path.isdir(path):
        return ("folder", 0, st.st_mode & 0o7777)
    return ("file", st.st_size, st.st_mode & 0o7777)


def check(archive, folder):
    folder = os.path.abspath(folder)
    top, base = os.path.basename(folder), os.path.dirname(folder)
    disk = {top: describe(folder)}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            disk[os.path.relpath(p, base)] = describe(p)
    entries, problems = {}, []
    with tarfile.open(archive) as t:
        for m in t:
            name = m.name.rstrip("/")
            if name.startswith("/") or ".." in name.split("/"):
                problems.append(f"unsafe entry {m.name}")
            if name.split("/")[0] != top:
                problems.append(f"entry outside {top}/: {m.name}")
            if os.path.basename(name).startswith("._"):
                problems.append(f"AppleDouble entry {m.name}")
            if m.isdir():
                entries[name] = ("folder", 0, m.mode & 0o7777)
            elif m.isfile():
                entries[name] = ("file", m.size, m.mode & 0o7777)
            else:
                problems.append(f"not a plain file or folder ({m.type!r}): {m.name}")
            if (m.uid, m.gid, m.uname, m.gname) != (0, 0, "root", "wheel"):
                problems.append(f"owner {m.uid}:{m.gid} {m.uname}:{m.gname}: {m.name}")
            machine = sorted(k for k in m.pax_headers if k.startswith(MACHINE_HEADERS))
            if machine:
                problems.append(f"machine metadata in {m.name}: {', '.join(machine)}")
    for rel in sorted(set(disk) | set(entries)):
        if rel not in entries:
            problems.append(f"missing from the archive: {rel}")
        elif rel not in disk:
            problems.append(f"only in the archive: {rel}")
        elif disk[rel] != entries[rel]:
            problems.append(f"differs: {rel}: folder {disk[rel]}, archive {entries[rel]}")
    return entries, problems


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    entries, problems = check(argv[1], argv[2])
    print(f"tarcheck: {len(entries)} archive entries match the folder; {len(problems)} problems")
    for p in problems[:40]:
        print("  " + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv)
