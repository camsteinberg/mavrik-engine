/* winelibs: a Windows program that makes Wine's own code open the Unix libraries Wine loads by file
 * name or links, and checks that each one works. Built for both Windows halves (mingw-w64 gcc) and
 * run by the wine gate, which also checks with dyld where each library was loaded from.
 *
 *   bcrypt-aes         AES-CBC through bcrypt, which Wine does with GnuTLS
 *   schannel           TLS client credentials through schannel, also GnuTLS
 *   vulkan             the Vulkan instance extensions, from MoltenVK through winevulkan
 *   freetype           the TrueType font families, which Wine reads with FreeType
 *   winegstreamer.dll  loads winegstreamer.so, which links GStreamer
 *   winedmo.dll        loads winedmo.so, which links FFmpeg
 *
 * Lines: "check\tNAME\tok|FAIL\tDETAIL", then "done\tFAILURES". Exit status: the number of failures. */
#define SECURITY_WIN32
#include <windows.h>
#include <bcrypt.h>
#include <sspi.h>
#include <schannel.h>
#include <stdio.h>
#include <string.h>

static int failures;

static void report(const char *name, int ok, const char *detail)
{
    printf("check\t%s\t%s\t%s\n", name, ok ? "ok" : "FAIL", detail);
    fflush(stdout);
    if (!ok) failures++;
}

static void check_bcrypt(void)
{
    BCRYPT_ALG_HANDLE alg = NULL;
    BCRYPT_KEY_HANDLE key = NULL;
    UCHAR secret[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}, iv[16] = {0};
    UCHAR data[16] = "mavrik engine!!", out[16] = {0};
    ULONG len = 0;
    char detail[128];
    NTSTATUS st = BCryptOpenAlgorithmProvider(&alg, BCRYPT_AES_ALGORITHM, NULL, 0);
    if (!st) st = BCryptSetProperty(alg, BCRYPT_CHAINING_MODE, (UCHAR *)BCRYPT_CHAIN_MODE_CBC,
                                    sizeof(BCRYPT_CHAIN_MODE_CBC), 0);
    if (!st) st = BCryptGenerateSymmetricKey(alg, &key, NULL, 0, secret, sizeof(secret), 0);
    if (!st) st = BCryptEncrypt(key, data, sizeof(data), NULL, iv, sizeof(iv), out, sizeof(out), &len, 0);
    snprintf(detail, sizeof(detail), "AES-CBC: status 0x%08lx, %lu bytes", (unsigned long)st, (unsigned long)len);
    report("bcrypt-aes", !st && len == sizeof(out) && memcmp(out, data, sizeof(out)), detail);
    if (key) BCryptDestroyKey(key);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
}

static void check_schannel(void)
{
    SCHANNEL_CRED cred = {0};
    CredHandle handle;
    TimeStamp expiry;
    char detail[128];
    SECURITY_STATUS st;
    cred.dwVersion = SCHANNEL_CRED_VERSION;
    cred.dwFlags = SCH_CRED_NO_DEFAULT_CREDS | SCH_CRED_MANUAL_CRED_VALIDATION;
    st = AcquireCredentialsHandleA(NULL, (char *)UNISP_NAME_A, SECPKG_CRED_OUTBOUND, NULL, &cred, NULL, NULL,
                                   &handle, &expiry);
    snprintf(detail, sizeof(detail), "client credentials: status 0x%08lx", (unsigned long)st);
    report("schannel", st == SEC_E_OK, detail);
    if (st == SEC_E_OK) FreeCredentialsHandle(&handle);
}

typedef int (WINAPI *enum_extensions_fn)(const char *, unsigned int *, void *);

static void check_vulkan(void)
{
    HMODULE vk = LoadLibraryA("vulkan-1.dll");
    enum_extensions_fn fn = vk ? (enum_extensions_fn)(void *)GetProcAddress(vk, "vkEnumerateInstanceExtensionProperties") : NULL;
    unsigned int count = 0;
    int res = -1;
    char detail[128];
    if (fn) res = fn(NULL, &count, NULL);
    snprintf(detail, sizeof(detail), "instance extensions: result %d, %u found", res, count);
    report("vulkan", fn && res == 0 && count > 0, detail);
}

static int CALLBACK count_truetype(const LOGFONTA *lf, const TEXTMETRICA *tm, DWORD type, LPARAM param)
{
    (void)lf;
    (void)tm;
    if (type & TRUETYPE_FONTTYPE) ++*(int *)param;
    return 1;
}

static void check_fonts(void)
{
    HDC dc = GetDC(NULL);
    LOGFONTA lf = {0};
    int truetype = 0;
    char detail[128];
    lf.lfCharSet = DEFAULT_CHARSET;
    EnumFontFamiliesExA(dc, &lf, (FONTENUMPROCA)count_truetype, (LPARAM)&truetype, 0);
    ReleaseDC(NULL, dc);
    snprintf(detail, sizeof(detail), "%d TrueType font families", truetype);
    report("freetype", truetype > 0, detail);
}

static void check_module(const char *name)
{
    HMODULE m = LoadLibraryA(name);
    char detail[128];
    snprintf(detail, sizeof(detail), m ? "loaded" : "not loaded (error %lu)", (unsigned long)GetLastError());
    report(name, m != NULL, detail);
}

int main(void)
{
    check_bcrypt();
    check_schannel();
    check_vulkan();
    check_fonts();
    check_module("winegstreamer.dll");
    check_module("winedmo.dll");
    printf("done\t%d\n", failures);
    fflush(stdout);
    return failures;
}
