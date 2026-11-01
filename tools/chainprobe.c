/* The gamemode gate's Windows program (patch 0037 version 3).
 *
 *   chainprobe.exe [NEXT [ARGS...]]   starts NEXT with ARGS as its arguments, waits for it to end and
 *                                     ends with its exit code; with no NEXT, ends at once
 *
 * The gate copies the 64- and 32-bit builds under names of its own and runs three in a row, so a program,
 * its child and its grandchild each start through a link (patch 0007) named after its own file, in the
 * link folder of the loader Wine started it from. Each child starts from the loader its parent chose, and inherits
 * MAVRIK_GAME_MODE with the rest of the Unix environment (Wine's spawn_process passes the parent's Unix environment,
 * not the Windows one), so the grandchild proves the variable passes through two generations.
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    STARTUPINFOA si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    char cmdline[4096];
    size_t used = 0;
    DWORD code = 0;
    int i;

    if (argc < 2)
    {
        printf("chain\tend\tok\n");
        return 0;
    }
    for (i = 1; i < argc; i++)
    {
        int n = snprintf(cmdline + used, sizeof(cmdline) - used, "%s\"%s\"", i > 1 ? " " : "", argv[i]);
        if (n < 0 || (size_t)n >= sizeof(cmdline) - used)
        {
            printf("chain\tstart\tfail\tcommand line too long\n");
            return 2;
        }
        used += n;
    }
    if (!CreateProcessA(argv[1], cmdline, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
    {
        printf("chain\tstart\tfail\tCreateProcess %s failed, error %lu\n", argv[1], GetLastError());
        return 3;
    }
    WaitForSingleObject(pi.hProcess, 60000);
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    printf("chain\tstart\tok\t%s exited %lu\n", argv[1], code);
    fflush(stdout);
    return (int)code;
}
