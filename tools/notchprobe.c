/* notchprobe.c -- what a Windows game sees of the display, for patch 0040 (FitBelowNotch).
 *
 * It prints, one tab-separated line each:
 *   mode     every mode EnumDisplaySettings lists for the primary display (WxH bpp Hz)
 *   current  ENUM_CURRENT_SETTINGS
 *   monitor  GetMonitorInfo of the primary monitor: rcMonitor and rcWork
 *   metrics  GetSystemMetrics' screen and virtual screen, GetDeviceCaps' HORZRES, VERTRES, DESKTOPVERTRES
 * then opens a borderless WS_POPUP window at the monitor rect (dark grey, a red bar on its top 8 rows) and prints
 *   hold     full: the window is up (a Mac-side reader may list the windows now; the probe waits 4 s)
 *   cursor   SetCursorPos then GetCursorPos at (10,0), the centre and (11,101): "set X,Y got X,Y"
 * then ChangeDisplaySettings to 1280x720 with CDS_FULLSCREEN, moves the window to the new monitor rect as games do,
 * and prints
 *   change   the call's result
 *   current, monitor, window (GetWindowRect)
 *   hold     1280: the scaled mode is up (4 s)
 * then restores the mode (ChangeDisplaySettings(NULL, 0)), prints "done", and exits.
 * "notchprobe.exe nochange" leaves out the mode change: without FitBelowNotch it would change the Mac's real mode.
 *
 * "notchprobe.exe ... strip" adds, after the cursor round trip, the pointer over the strip beside the camera
 * housing. The probe registers for raw mouse input (WM_INPUT, as a game's mouse-look and Wine's DirectInput mouse
 * read it), hides its cursor and clips it to the monitor (a full-screen game's usual state; a clip of the whole
 * monitor is no confinement), and prints one "hold strip-NAME" line per phase, then counts raw input for 3 s while
 * a Mac-side tool posts that phase's pointer moves (the notch kit's stripmove: "in" up into the strip, "h" across
 * it, "down" down it and out of it), then prints
 *   raw      NAME: events, the sums of lLastX and lLastY, the count of moves up (lLastY < 0) and down, the least lLastY
 * Then it shows its cursor, lifts the clip and prints "hold strip-rest": the tool leaves the pointer resting in
 * the strip, and after 1.5 s (Wine 11 then takes the driver's position, not the server's) it prints
 *   rest     GetCursorPos and the monitor's top: with FitBelowNotch the position is at the monitor's top edge
 * A second display (an external one above the built-in, or a notched one that isn't the main display) needs one
 * plugged in: then EnumDisplayMonitors and GetMonitorInfo of each should place each where macOS has it.
 *
 * It draws, so it runs with the Mac display driver on, in an away block (the screen unlocked, nobody at the Mac).
 *
 * Build: i686-w64-mingw32-gcc or x86_64-w64-mingw32-gcc -O1 -s -o notchprobe.exe notchprobe.c -lgdi32 -luser32
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>

/* raw mouse input, counted between strip phases */
static struct { LONG events, dx, dy, up, down, least_dy; } raw;

static void pump(DWORD ms)
{
    DWORD end = GetTickCount() + ms;
    MSG msg;

    while ((LONG)(end - GetTickCount()) > 0)
    {
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE))
        {
            TranslateMessage(&msg);
            DispatchMessageA(&msg);
        }
        Sleep(10);
    }
}

static LRESULT CALLBACK wndproc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    if (msg == WM_PAINT)
    {
        PAINTSTRUCT ps;
        RECT rc, bar;
        HDC hdc = BeginPaint(hwnd, &ps);
        HBRUSH grey = CreateSolidBrush(RGB(40, 40, 40)), red = CreateSolidBrush(RGB(255, 0, 0));

        GetClientRect(hwnd, &rc);
        FillRect(hdc, &rc, grey);
        bar = rc;
        bar.bottom = bar.top + 8;
        FillRect(hdc, &bar, red);
        DeleteObject(grey);
        DeleteObject(red);
        EndPaint(hwnd, &ps);
        return 0;
    }
    if (msg == WM_INPUT)
    {
        RAWINPUT ri;
        UINT size = sizeof(ri);

        if (GetRawInputData((HRAWINPUT)lp, RID_INPUT, &ri, &size, sizeof(RAWINPUTHEADER)) != (UINT)-1 &&
            ri.header.dwType == RIM_TYPEMOUSE && !(ri.data.mouse.usFlags & MOUSE_MOVE_ABSOLUTE) &&
            (ri.data.mouse.lLastX || ri.data.mouse.lLastY))
        {
            raw.events++;
            raw.dx += ri.data.mouse.lLastX;
            raw.dy += ri.data.mouse.lLastY;
            if (ri.data.mouse.lLastY < 0) raw.up++;
            if (ri.data.mouse.lLastY > 0) raw.down++;
            if (ri.data.mouse.lLastY < raw.least_dy) raw.least_dy = ri.data.mouse.lLastY;
        }
        return DefWindowProcA(hwnd, msg, wp, lp);
    }
    if (msg == WM_SETCURSOR)
    {
        SetCursor(LoadCursor(NULL, IDC_ARROW));
        return TRUE;
    }
    return DefWindowProcA(hwnd, msg, wp, lp);
}

static void print_current(void)
{
    DEVMODEA dm = { .dmSize = sizeof(dm) };

    if (EnumDisplaySettingsA(NULL, ENUM_CURRENT_SETTINGS, &dm))
        printf("current\t%lux%lu\t%lu bpp\t%lu Hz\tposition %ld,%ld\n", dm.dmPelsWidth, dm.dmPelsHeight,
               dm.dmBitsPerPel, dm.dmDisplayFrequency, dm.dmPosition.x, dm.dmPosition.y);
    else
        printf("current\tfailed %lu\n", GetLastError());
}

static RECT print_monitor(void)
{
    MONITORINFO mi = { .cbSize = sizeof(mi) };
    POINT origin = { 0, 0 };
    HMONITOR mon = MonitorFromPoint(origin, MONITOR_DEFAULTTOPRIMARY);

    GetMonitorInfoA(mon, &mi);
    printf("monitor\t%ld,%ld,%ld,%ld\twork %ld,%ld,%ld,%ld\tsize %ldx%ld\n",
           mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom,
           mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom,
           mi.rcMonitor.right - mi.rcMonitor.left, mi.rcMonitor.bottom - mi.rcMonitor.top);
    return mi.rcMonitor;
}

static void cursor_round_trip(int x, int y)
{
    POINT pt = { -1, -1 };

    SetCursorPos(x, y);
    pump(100);
    GetCursorPos(&pt);
    printf("cursor\tset %d,%d got %ld,%ld\t%s\n", x, y, pt.x, pt.y, pt.x == x && pt.y == y ? "exact" : "differs");
}

static void strip_phase(const char *name)
{
    memset(&raw, 0, sizeof(raw));
    printf("hold\tstrip-%s\n", name);
    fflush(stdout);
    pump(3000);
    printf("raw\t%s\tevents %ld\tdx %ld\tdy %ld\tup %ld\tdown %ld\tleast dy %ld\n", name, raw.events, raw.dx, raw.dy,
           raw.up, raw.down, raw.least_dy);
    fflush(stdout);
}

static void strip_checks(HWND hwnd, RECT mon)
{
    RAWINPUTDEVICE rid = { 1, 2, 0, hwnd };   /* the generic desktop page's mouse */
    POINT pt = { -1, -1 };

    if (!RegisterRawInputDevices(&rid, 1, sizeof(rid)))
        printf("raw\tregister failed %lu\n", GetLastError());
    while (ShowCursor(FALSE) >= 0) ;
    ClipCursor(&mon);
    strip_phase("in");
    strip_phase("h");
    strip_phase("down");
    ClipCursor(NULL);
    while (ShowCursor(TRUE) < 0) ;
    printf("hold\tstrip-rest\n");
    fflush(stdout);
    pump(1500);
    GetCursorPos(&pt);
    printf("rest\tgot %ld,%ld\tmonitor top %ld\t%s\n", pt.x, pt.y, mon.top, pt.y >= mon.top ? "on the monitor" : "above it");
    fflush(stdout);
}

int main(int argc, char **argv)
{
    DEVMODEA dm = { .dmSize = sizeof(dm) };
    WNDCLASSA wc = { 0 };
    HDC screen;
    HWND hwnd;
    RECT mon, wr;
    LONG rc;
    DWORD i;

    SetProcessDPIAware();
    for (i = 0; EnumDisplaySettingsA(NULL, i, &dm); i++)
        printf("mode\t%lux%lu\t%lu bpp\t%lu Hz\n", dm.dmPelsWidth, dm.dmPelsHeight, dm.dmBitsPerPel, dm.dmDisplayFrequency);
    printf("modes\t%lu\n", i);
    print_current();
    mon = print_monitor();
    screen = GetDC(NULL);
    printf("metrics\tscreen %dx%d\tvirtual %d,%d %dx%d\tHORZRES %d VERTRES %d DESKTOPVERTRES %d\n",
           GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN),
           GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN),
           GetSystemMetrics(SM_CXVIRTUALSCREEN), GetSystemMetrics(SM_CYVIRTUALSCREEN),
           GetDeviceCaps(screen, HORZRES), GetDeviceCaps(screen, VERTRES), GetDeviceCaps(screen, DESKTOPVERTRES));
    ReleaseDC(NULL, screen);
    fflush(stdout);

    wc.lpfnWndProc = wndproc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "mavrik notch probe";
    RegisterClassA(&wc);
    hwnd = CreateWindowExA(0, wc.lpszClassName, "mavrik notch probe", WS_POPUP | WS_VISIBLE,
                           mon.left, mon.top, mon.right - mon.left, mon.bottom - mon.top, NULL, NULL, wc.hInstance, NULL);
    SetForegroundWindow(hwnd);
    pump(1000);
    GetWindowRect(hwnd, &wr);
    printf("window\t%ld,%ld,%ld,%ld\n", wr.left, wr.top, wr.right, wr.bottom);
    printf("hold\tfull\n");
    fflush(stdout);
    pump(4000);

    cursor_round_trip(10, 0);
    cursor_round_trip((mon.left + mon.right) / 2, (mon.top + mon.bottom) / 2);
    cursor_round_trip(11, 101);   /* odd: a half point in Retina mode, with or without FitBelowNotch */
    fflush(stdout);

    for (i = 1; i < (DWORD)argc; i++)
        if (!strcmp(argv[i], "strip")) strip_checks(hwnd, mon);

    if (argc > 1 && !strcmp(argv[1], "nochange"))
    {
        DestroyWindow(hwnd);
        pump(300);
        printf("done\n");
        fflush(stdout);
        return 0;
    }

    memset(&dm, 0, sizeof(dm));
    dm.dmSize = sizeof(dm);
    dm.dmPelsWidth = 1280;
    dm.dmPelsHeight = 720;
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT;
    rc = ChangeDisplaySettingsA(&dm, CDS_FULLSCREEN);
    printf("change\t1280x720\t%ld\n", rc);
    pump(500);
    print_current();
    mon = print_monitor();
    SetWindowPos(hwnd, HWND_TOP, mon.left, mon.top, mon.right - mon.left, mon.bottom - mon.top, SWP_SHOWWINDOW);
    pump(1000);
    GetWindowRect(hwnd, &wr);
    printf("window\t%ld,%ld,%ld,%ld\n", wr.left, wr.top, wr.right, wr.bottom);
    printf("hold\t1280\n");
    fflush(stdout);
    pump(4000);

    rc = ChangeDisplaySettingsA(NULL, 0);
    printf("restore\t%ld\n", rc);
    DestroyWindow(hwnd);
    pump(300);
    printf("done\n");
    fflush(stdout);
    return 0;
}
