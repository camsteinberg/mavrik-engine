/* The dockname gate's reader of two names macOS keeps for a process:
 *
 *   procnames PID...   prints, for each PID, one line: PID, the window server's owner name of its
 *                      windows (kCGWindowOwnerName, what the menu bar and Cmd-Tab show), and its
 *                      executable path (proc_pidpath), tab separated; "-" where there is none
 *
 * It only reads: CGWindowListCopyWindowInfo's list, for the given processes' windows. No screen
 * capture (an owner name needs no screen recording permission), no window title.
 */
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <libproc.h>
#include <stdio.h>
#include <stdlib.h>

static void owner_name(CFArrayRef windows, int pid, char *buf, size_t len)
{
    snprintf(buf, len, "-");
    for (CFIndex i = 0; windows && i < CFArrayGetCount(windows); i++)
    {
        CFDictionaryRef w = CFArrayGetValueAtIndex(windows, i);
        CFNumberRef owner = CFDictionaryGetValue(w, kCGWindowOwnerPID);
        CFStringRef name = CFDictionaryGetValue(w, kCGWindowOwnerName);
        int owner_pid;

        if (!owner || !CFNumberGetValue(owner, kCFNumberIntType, &owner_pid) || owner_pid != pid)
            continue;
        if (name && CFStringGetCString(name, buf, len, kCFStringEncodingUTF8))
            return;
    }
}

int main(int argc, char **argv)
{
    CFArrayRef windows = CGWindowListCopyWindowInfo(kCGWindowListOptionAll, kCGNullWindowID);

    for (int i = 1; i < argc; i++)
    {
        int pid = atoi(argv[i]);
        char name[1024], path[PROC_PIDPATHINFO_MAXSIZE];

        owner_name(windows, pid, name, sizeof(name));
        if (proc_pidpath(pid, path, sizeof(path)) <= 0)
            snprintf(path, sizeof(path), "-");
        printf("%d\t%s\t%s\n", pid, name, path);
    }
    if (windows)
        CFRelease(windows);
    return 0;
}
