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
highball-engine since September 2026.
