/* d3d11probe: a Windows program that draws through Direct3D 11 the way a game does, run by the d3d11
 * gate in the 64-bit half. In this engine Direct3D 11 is DXMT, which draws with Metal into a Metal
 * view it puts in the game's window through winemac.so's macdrv_functions.
 *
 *   device      D3D11CreateDeviceAndSwapChain on a visible window: a hardware device at feature
 *               level 11_0 or better, and its adapter's name
 *   present     60 frames cleared and presented to the window's swap chain (the Metal view)
 *   readback    a render target cleared to a known colour, copied to a staging texture and read on
 *               the CPU: the GPU really ran the commands
 *
 * Lines: "check\tNAME\tok|FAIL\tDETAIL", then "done\tFAILURES". Exit status: the number of failures. */
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <stdio.h>

static int failures;

static void report(const char *name, int ok, const char *detail)
{
    printf("check\t%s\t%s\t%s\n", name, ok ? "ok" : "FAIL", detail);
    fflush(stdout);
    if (!ok) failures++;
}

static void pump(void)
{
    MSG msg;
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE))
    {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

static void readback(ID3D11Device *dev, ID3D11DeviceContext *ctx)
{
    static const float colour[4] = {0.25f, 0.5f, 0.75f, 1.0f};
    D3D11_TEXTURE2D_DESC desc = {0};
    ID3D11Texture2D *target = NULL, *staging = NULL;
    ID3D11RenderTargetView *rtv = NULL;
    D3D11_MAPPED_SUBRESOURCE map;
    char detail[160] = "could not create the textures";
    HRESULT hr;

    desc.Width = desc.Height = 64;
    desc.MipLevels = desc.ArraySize = 1;
    desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.Usage = D3D11_USAGE_DEFAULT;
    desc.BindFlags = D3D11_BIND_RENDER_TARGET;
    hr = ID3D11Device_CreateTexture2D(dev, &desc, NULL, &target);
    if (SUCCEEDED(hr)) hr = ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)target, NULL, &rtv);
    desc.Usage = D3D11_USAGE_STAGING;
    desc.BindFlags = 0;
    desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    if (SUCCEEDED(hr)) hr = ID3D11Device_CreateTexture2D(dev, &desc, NULL, &staging);
    if (SUCCEEDED(hr))
    {
        ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, colour);
        ID3D11DeviceContext_CopyResource(ctx, (ID3D11Resource *)staging, (ID3D11Resource *)target);
        hr = ID3D11DeviceContext_Map(ctx, (ID3D11Resource *)staging, 0, D3D11_MAP_READ, 0, &map);
        if (SUCCEEDED(hr))
        {
            const BYTE *p = (const BYTE *)map.pData + 17 * map.RowPitch + 23 * 4;
            int ok = abs(p[0] - 64) <= 1 && abs(p[1] - 128) <= 1 && abs(p[2] - 191) <= 1 && p[3] == 255;
            snprintf(detail, sizeof(detail), "pixel (23,17) is %u,%u,%u,%u, cleared to 64,128,191,255", p[0], p[1], p[2], p[3]);
            ID3D11DeviceContext_Unmap(ctx, (ID3D11Resource *)staging, 0);
            report("readback", ok, detail);
        }
        else
        {
            snprintf(detail, sizeof(detail), "Map failed: 0x%08lx", (unsigned long)hr);
            report("readback", 0, detail);
        }
    }
    else
    {
        snprintf(detail, sizeof(detail), "creating the textures failed: 0x%08lx", (unsigned long)hr);
        report("readback", 0, detail);
    }
    if (staging) ID3D11Texture2D_Release(staging);
    if (rtv) ID3D11RenderTargetView_Release(rtv);
    if (target) ID3D11Texture2D_Release(target);
}

int main(void)
{
    static const D3D_FEATURE_LEVEL levels[] = {D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0};
    static const float colours[2][4] = {{0.1f, 0.4f, 0.8f, 1.0f}, {0.8f, 0.4f, 0.1f, 1.0f}};
    WNDCLASSW wc = {0};
    DXGI_SWAP_CHAIN_DESC sd = {0};
    IDXGISwapChain *swap = NULL;
    ID3D11Device *dev = NULL;
    ID3D11DeviceContext *ctx = NULL;
    D3D_FEATURE_LEVEL level = 0;
    char detail[256];
    HWND hwnd;
    HRESULT hr;
    int i, presented = 0;

    wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"d3d11probe";
    RegisterClassW(&wc);
    hwnd = CreateWindowExW(0, L"d3d11probe", L"d3d11probe", WS_OVERLAPPEDWINDOW, 40, 40, 256, 256,
                           NULL, NULL, wc.hInstance, NULL);
    ShowWindow(hwnd, SW_SHOWNOACTIVATE);
    UpdateWindow(hwnd);
    pump();

    sd.BufferDesc.Width = 256;
    sd.BufferDesc.Height = 256;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.OutputWindow = hwnd;
    sd.Windowed = TRUE;
    sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
    hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, levels, 2, D3D11_SDK_VERSION,
                                       &sd, &swap, &dev, &level, &ctx);
    if (FAILED(hr))
    {
        snprintf(detail, sizeof(detail), "D3D11CreateDeviceAndSwapChain failed: 0x%08lx", (unsigned long)hr);
        report("device", 0, detail);
    }
    else
    {
        IDXGIDevice *dxgi = NULL;
        IDXGIAdapter *adapter = NULL;
        DXGI_ADAPTER_DESC ad = {0};
        char name[128] = "?";
        if (SUCCEEDED(ID3D11Device_QueryInterface(dev, &IID_IDXGIDevice, (void **)&dxgi))
            && SUCCEEDED(IDXGIDevice_GetAdapter(dxgi, &adapter)) && SUCCEEDED(IDXGIAdapter_GetDesc(adapter, &ad)))
            WideCharToMultiByte(CP_UTF8, 0, ad.Description, -1, name, sizeof(name), NULL, NULL);
        if (adapter) IDXGIAdapter_Release(adapter);
        if (dxgi) IDXGIDevice_Release(dxgi);
        snprintf(detail, sizeof(detail), "feature level 0x%x on \"%s\"", level, name);
        report("device", level >= D3D_FEATURE_LEVEL_11_0, detail);

        for (i = 0; i < 60; i++)
        {
            ID3D11Texture2D *back = NULL;
            ID3D11RenderTargetView *rtv = NULL;
            hr = IDXGISwapChain_GetBuffer(swap, 0, &IID_ID3D11Texture2D, (void **)&back);
            if (SUCCEEDED(hr)) hr = ID3D11Device_CreateRenderTargetView(dev, (ID3D11Resource *)back, NULL, &rtv);
            if (SUCCEEDED(hr))
            {
                ID3D11DeviceContext_OMSetRenderTargets(ctx, 1, &rtv, NULL);
                ID3D11DeviceContext_ClearRenderTargetView(ctx, rtv, colours[i & 1]);
                hr = IDXGISwapChain_Present(swap, 1, 0);
            }
            if (rtv) ID3D11RenderTargetView_Release(rtv);
            if (back) ID3D11Texture2D_Release(back);
            if (FAILED(hr)) break;
            presented++;
            pump();
        }
        if (FAILED(hr))
            snprintf(detail, sizeof(detail), "%d of 60 frames presented, then 0x%08lx", presented, (unsigned long)hr);
        else
            snprintf(detail, sizeof(detail), "%d of 60 frames presented", presented);
        report("present", presented == 60, detail);

        readback(dev, ctx);
        ID3D11DeviceContext_ClearState(ctx);
        ID3D11DeviceContext_Release(ctx);
        IDXGISwapChain_Release(swap);
        ID3D11Device_Release(dev);
    }
    DestroyWindow(hwnd);
    pump();
    printf("done\t%d\n", failures);
    fflush(stdout);
    return failures;
}
