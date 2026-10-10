/* The bridge's steamredirect gate: Valve's loader change (the engine's patch 0004) with the real
 * lsteamclient, in one half of Wine. No Steam is needed, and none is touched.
 *
 * Built two ways for each half:
 *   -DPROBE_DLL -shared, as steamclient.dll (32-bit) or steamclient64.dll (64-bit): a stand-in for
 *     Valve's file, exporting Steam_IsKnownInterface, which lsteamclient exports too. Its own answer is 7.
 *   no define, as bridgeprobe32.exe or bridgeprobe64.exe: loads the stand-in from its own folder.
 * With the bridge, loading the stand-in loads lsteamclient.dll from the engine, and the stand-in's export
 * jumps into lsteamclient's. lsteamclient's Windows half then calls its Unix half (lsteamclient.so,
 * through the 64-bit call table or, in a 32-bit program, the wow64 one). The gate points
 * STEAM_COMPAT_CLIENT_INSTALL_PATH at a stand-in Steam library (lsteamclient aborts without one) that,
 * like the Mac Steam app's, lacks Steam_IsKnownInterface; the Unix half then answers 1 ("every
 * interface is known", mavrik's patch for a Steam library without the function).
 * Three checks, in order, each printed as a "check" line, then "done":
 *   redirect  lsteamclient.dll is loaded and the stand-in's export is still at its own address
 *   unixlib   lsteamclient.dll's Unix half is loaded, with its call table (Wine's own query)
 *   call      the export answered 1, which only lsteamclient's Unix half gives
 */
#include <windows.h>
#include <stdio.h>

#ifdef PROBE_DLL

__declspec(dllexport) signed char __cdecl Steam_IsKnownInterface(const char *version)
{
    /* volatile keeps the function longer than the jump the loader writes over its start */
    volatile signed char value = 7;
    return version ? value : value + 1;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void *reserved)
{
    return TRUE;
}

#else

#define MemoryWineUnixFuncs 1000  /* Wine's own class (include/winternl.h); wow64 maps it for 32-bit */

typedef LONG (WINAPI *query_t)(HANDLE, void *, int, void *, SIZE_T, SIZE_T *);

int main(void)
{
    const char *name = sizeof(void *) == 8 ? "steamclient64.dll" : "steamclient.dll";
    HMODULE module = LoadLibraryA(name), bridge;
    IMAGE_NT_HEADERS *nt;
    signed char (__cdecl *known)(const char *);
    query_t query = (query_t)GetProcAddress(GetModuleHandleA("ntdll.dll"), "NtQueryVirtualMemory");
    ULONGLONG handle = 0;
    LONG status = -1;
    BOOL inside;
    int value;

    if (!module || !(known = (void *)GetProcAddress(module, "Steam_IsKnownInterface")))
    {
        printf("check\tredirect\tfail\tLoadLibrary(%s) or its export failed, error %lu\n", name, GetLastError());
        printf("done\t%s\n", name);
        return 1;
    }
    nt = (IMAGE_NT_HEADERS *)((BYTE *)module + ((IMAGE_DOS_HEADER *)module)->e_lfanew);
    inside = (BYTE *)known >= (BYTE *)module && (BYTE *)known < (BYTE *)module + nt->OptionalHeader.SizeOfImage;
    bridge = GetModuleHandleA("lsteamclient.dll");
    printf("check\tredirect\t%s\tlsteamclient.dll loaded: %s, %s's export at its own address: %s\n",
           bridge && inside ? "ok" : "fail", bridge ? "yes" : "no", name, inside ? "yes" : "no");
    if (!bridge)
    {
        printf("done\t%s\n", name);
        return 1;
    }
    if (query) status = query(GetCurrentProcess(), bridge, MemoryWineUnixFuncs, &handle, sizeof(handle), NULL);
    printf("check\tunixlib\t%s\tlsteamclient's Unix half: status 0x%08lx, call table %s\n",
           !status && handle ? "ok" : "fail", (unsigned long)status, handle ? "found" : "missing");
    if (status || !handle)
    {
        printf("done\t%s\n", name);
        return 1;
    }
    value = known("SteamClient017");
    printf("check\tcall\t%s\tSteam_IsKnownInterface answered %d (lsteamclient's Unix half: 1, the stand-in: 7)\n",
           value == 1 ? "ok" : "fail", value);
    printf("done\t%s\n", name);
    return 0;
}

#endif
