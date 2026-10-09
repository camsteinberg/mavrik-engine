/* The steamredirect gate's Windows program and its two DLLs, from this one file.
 *
 * Valve's loader change (patch 0004): when Wine loads a DLL named steamclient or steamclient64, it
 * loads lsteamclient.dll as well and makes each of the first DLL's exports jump to lsteamclient's
 * export of the same name. Built three ways for each half of Wine:
 *   -DPROBE_DLL=1 -shared, as steamclient.dll (32-bit) or steamclient64.dll (64-bit): Valve's file
 *   -DPROBE_DLL=2 -shared, as lsteamclient.dll: the bridge
 *   no define, as steamprobe32.exe or steamprobe64.exe: loads the steamclient DLL from its own folder
 *     and calls its export SteamProbeValue
 * With the redirect, the call goes to an address inside the steamclient DLL and returns 2,
 * lsteamclient's value. Prints one "check" line and "done", as the gates read.
 */
#include <windows.h>
#include <stdio.h>

#ifdef PROBE_DLL

__declspec(dllexport) int __cdecl SteamProbeValue(void)
{
    /* volatile keeps the function longer than the 12-byte jump the loader writes over its start */
    volatile int value = PROBE_DLL;
    return value;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void *reserved)
{
    return TRUE;
}

#else

int main(void)
{
    const char *name = sizeof(void *) == 8 ? "steamclient64.dll" : "steamclient.dll";
    HMODULE module = LoadLibraryA(name);
    IMAGE_NT_HEADERS *nt;
    int (__cdecl *probe)(void);
    BOOL inside;
    int value;

    if (!module)
    {
        printf("check\tredirect\tfail\tLoadLibrary(%s) failed, error %lu\n", name, GetLastError());
        printf("done\t%s\n", name);
        return 1;
    }
    probe = (int (__cdecl *)(void))GetProcAddress(module, "SteamProbeValue");
    if (!probe)
    {
        printf("check\tredirect\tfail\t%s has no SteamProbeValue\n", name);
        printf("done\t%s\n", name);
        return 1;
    }
    nt = (IMAGE_NT_HEADERS *)((BYTE *)module + ((IMAGE_DOS_HEADER *)module)->e_lfanew);
    inside = (BYTE *)probe >= (BYTE *)module && (BYTE *)probe < (BYTE *)module + nt->OptionalHeader.SizeOfImage;
    value = probe();
    printf("check\tredirect\t%s\t%s's export returned %d (lsteamclient's value is 2, its own 1), "
           "address inside %s: %s, lsteamclient.dll loaded: %s\n",
           value == 2 && inside && GetModuleHandleA("lsteamclient.dll") ? "ok" : "fail", name, value, name,
           inside ? "yes" : "no", GetModuleHandleA("lsteamclient.dll") ? "yes" : "no");
    printf("done\t%s\n", name);
    return 0;
}

#endif
