"""closure.py REPO COMMIT: dlls/winecrt0's files and every header they include, transitively (all #include lines,
whatever #if they sit under), resolved as Wine's PE build does: "x" in the file's own folder, then include/ and
include/msvcrt/; <x> in include/msvcrt/ and include/. A header that is generated (x.h from x.idl, or config.h from
config.h.in) brings its source. Prints the paths; unresolved names go to stderr (system or compiler headers)."""
import re, subprocess, sys, posixpath
repo, commit = sys.argv[1], sys.argv[2]
tree = set(subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", commit], capture_output=True, text=True, check=True).stdout.split("\n"))
def read(p):
    return subprocess.run(["git", "-C", repo, "show", f"{commit}:{p}"], capture_output=True, text=True, errors="replace", check=True).stdout
INC = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', re.M)
IMP = re.compile(r'^\s*import\s+"([^"]+)"', re.M)
todo = sorted(p for p in tree if p.startswith("dlls/winecrt0/"))
seen, missing = set(), set()
def resolve(name, here, quoted):
    dirs = ([here] if quoted else []) + (["include", "include/msvcrt"] if quoted else ["include/msvcrt", "include"])
    for d in dirs:
        for cand in (posixpath.normpath(posixpath.join(d, name)),):
            if cand in tree: return [cand]
            base, ext = posixpath.splitext(cand)
            if ext == ".h" and base + ".idl" in tree: return [base + ".idl"]
            if cand + ".in" in tree: return [cand + ".in"]
    return []
while todo:
    p = todo.pop()
    if p in seen: continue
    seen.add(p)
    if not p.endswith((".c", ".h", ".idl", ".in", ".S", ".s")): continue
    text = read(p)
    names = [(q == '"', n) for q, n in INC.findall(text)] + ([(True, n) for n in IMP.findall(text)] if p.endswith(".idl") else [])
    for quoted, n in names:
        r = resolve(n, posixpath.dirname(p), quoted)
        if r: todo.extend(x for x in r if x not in seen)
        else: missing.add(n)
for p in sorted(seen): print(p)
print("unresolved: " + " ".join(sorted(missing)), file=sys.stderr)
