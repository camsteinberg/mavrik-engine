# Draft for upstream Wine: patch 0004

Status: draft, not sent. Who sends it is still open: Alexander Theissen wrote the change, so the
cleanest route is that he sends it himself; otherwise it goes with him named as its author.

---

**ntdll: Return no alternate loader when it does not exist.**

On an installation built for new WoW64 only (no lib/wine/i386-unix, which is every current macOS
build), get_alternate_wineloader() still returns lib/wine/i386-unix/wine for a 32-bit image.
build_initial_params() treats any non-NULL return as a reason to relaunch through start.exe /exec,
so `wine program32.exe` runs as two processes: start.exe, and the program as a separate process
whose Unix parent is launchd, inside start.exe's job. loader_exec() also tries to exec the missing
loader before falling back to the 64-bit one.

WINEARCH=wow64 avoids this, as suggested in bug 59080, but users of a wow64-only build have no
reason to know they need it, and the build has only one loader to run.

This checks the loader with access(X_OK) before returning it, so a wow64-only installation behaves
as with WINEARCH=wow64. 64-bit images never reach the check; installations with a 32-bit Unix loader
are unchanged. (It does not address bug 59080, where the loader exists but cannot run.)

The change is Alexander Theissen's (part of a4e40c6 in github.com/athei/wine), shipped in
highball-engine since September 2026. Tested on Wine 11.0 from CrossOver 26.3.0 sources under
Rosetta on macOS 26.4: syswow64\notepad.exe runs as one process instead of two, 64-bit programs
are unchanged, and a 32-bit program started from a 64-bit one still runs.

---

Evidence behind the last sentence (not part of the note): mavrik-engine revision 2 (recipe
6cff7e5) against revision 1, same lab and harness, 2026-10-06, `WINEARCH=win64`.
- `wine C:\windows\syswow64\notepad.exe`, three runs each: revision 1 ran it under
  `start.exe /exec` (the launched process), the program as a separate process whose parent is
  launchd, 10 Wine processes; revision 2 ran it in the launched process itself, no start.exe,
  9 processes. Revision 1 with `WINEARCH=wow64` behaved like revision 2.
- `cmd /c exit 7` and `cmd /c echo`, 32- and 64-bit: the exit code 7 and the output arrive the
  same way on both revisions.
- 64-bit Notepad, and 32-bit Notepad started by 64-bit cmd: the same on both revisions.
- A 32-bit Direct3D 11 test program (Wine's wined3d), started directly, two 10 s runs each: a
  window, frames presented, exit code 0 on both revisions. Started once more and stopped: on
  revision 1 it ran under `start.exe /exec` as a separate process (10 Wine processes), on
  revision 2 as the launched process itself (9).
- The 13 Notepad runs (32-bit, 64-bit, and 32-bit started by cmd) and the two stopped Direct3D
  runs were stopped by asking the program to quit as the Dock's Quit does, then ending the
  prefix's remaining programs and its server; nothing of the prefix ran 10 s later, on both
  revisions. The cmd runs and the plain Direct3D runs ended by themselves and were checked after
  `wineserver -k`; they were not stopped.
