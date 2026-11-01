/* The gamemode gate's Windows program (patch 0037 version 3).
 *
 *   chainprobe.exe [NEXT [ARGS...]]   starts NEXT with ARGS as its arguments, waits for it to end and
 *                                     ends with its exit code; with no NEXT, ends at once
 *
 * The gate copies the 64- and 32-bit builds under names of its own and runs three in a row, so a program,
 * its child and its grandchild each start through a link (patch 0007) named after its own file, in the
 * link folder of the loader Wine started it from. The grandchild shows the choice the child made from the
 * environment it was given, so MAVRIK_GAME_MODE must have passed through the Windows environment.
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
