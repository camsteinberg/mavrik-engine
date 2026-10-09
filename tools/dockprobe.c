/* The dockname gate's Windows program.
 *
 *   dockprobe64.exe CHILD   shows a window, then starts CHILD (dockprobe32.exe, a 32-bit program),
 *                           as a game's launcher starts the game
 *   dockprobe32.exe         shows a window
 *
 * Each keeps its window up for 40 s, or until the gate ends the prefix. Meanwhile the gate reads each
 * process's name in LaunchServices, the name the Dock and the app switcher show.
 */
#include <windows.h>
#include <stdio.h>

static LRESULT CALLBACK window_proc(HWND window, UINT msg, WPARAM wparam, LPARAM lparam)
{
    if (msg == WM_TIMER || msg == WM_CLOSE)
    {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(window, msg, wparam, lparam);
}

int main(int argc, char **argv)
{
    WNDCLASSA cls = {0};
    HWND window;
    MSG msg;

    cls.lpfnWndProc = window_proc;
    cls.hInstance = GetModuleHandleA(NULL);
    cls.lpszClassName = "dockprobe";
    cls.hCursor = LoadCursorA(NULL, (LPCSTR)IDC_ARROW);
    RegisterClassA(&cls);
    window = CreateWindowA("dockprobe", "dockprobe", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 320, 200,
                           NULL, NULL, cls.hInstance, NULL);
    if (!window)
    {
        printf("check\twindow\tfail\tCreateWindow failed, error %lu\n", GetLastError());
        return 1;
    }
    UpdateWindow(window);
    printf("check\twindow\tok\tshown\n");
    if (argc > 1)
    {
        STARTUPINFOA si = {sizeof(si)};
        PROCESS_INFORMATION pi;
        if (CreateProcessA(argv[1], NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi))
        {
            printf("check\tchild\tok\tstarted\n");
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
        else
            printf("check\tchild\tfail\tCreateProcess failed, error %lu\n", GetLastError());
    }
    fflush(stdout);
    SetTimer(window, 1, 40000, NULL);
    while (GetMessageA(&msg, NULL, 0, 0) > 0)
    {
        TranslateMessage(&msg);
        DispatchMessageA(&msg);
    }
    printf("done\tdockprobe\n");
    return 0;
}
