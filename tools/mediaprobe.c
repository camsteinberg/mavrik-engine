/* mediaprobe FILE: a Windows program that plays a movie through Wine's media code the two ways games
 * do, decoding every frame without showing it. Built for both Windows halves and run by the playback
 * gate on tools/media/sample.mp4 (1 s of H.264 video and AAC audio).
 *
 *   mf-video    Media Foundation's source reader (MFCreateSourceReaderFromURL), video decoded to NV12:
 *               Wine's H.264 decoder runs on GStreamer (winegstreamer)
 *   mf-audio    the same reader, audio decoded to 16-bit PCM (Wine's AAC decoder, also GStreamer)
 *   wm-video    the Windows Media sync reader (wmvcore's WMCreateSyncReader), which DirectShow-era games
 *               use: GStreamer demuxes and decodes the whole file (winegstreamer's parser)
 *   wm-audio    the same reader's audio output
 *
 * Lines: "check\tNAME\tok|FAIL\tDETAIL", then "done\tFAILURES". Exit status: the number of failures. */
#define COBJMACROS
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mferror.h>
#include <wmsdk.h>
#include <stdio.h>

#ifndef NS_E_NO_MORE_SAMPLES
#define NS_E_NO_MORE_SAMPLES ((HRESULT)0xc00d0bcfL)
#endif

static int failures;

static void report(const char *name, int ok, const char *detail)
{
    printf("check\t%s\t%s\t%s\n", name, ok ? "ok" : "FAIL", detail);
    fflush(stdout);
    if (!ok) failures++;
}

/* Reads one stream of the source reader to its end; returns the number of samples, or -1. */
static int read_stream(IMFSourceReader *reader, DWORD stream, HRESULT *last, LONGLONG *end)
{
    int samples = 0;
    *end = 0;
    for (;;)
    {
        DWORD index = 0, flags = 0;
        LONGLONG ts = 0;
        IMFSample *sample = NULL;
        *last = IMFSourceReader_ReadSample(reader, stream, 0, &index, &flags, &ts, &sample);
        if (FAILED(*last)) return -1;
        if (sample)
        {
            samples++;
            *end = ts;
            IMFSample_Release(sample);
        }
        if (flags & MF_SOURCE_READERF_ENDOFSTREAM) return samples;
        if (flags & MF_SOURCE_READERF_ERROR) return -1;
        if (samples > 10000) return samples;
    }
}

static void check_mf(const WCHAR *file)
{
    static const struct { const char *name; DWORD stream; const GUID *major, *subtype; int least; } streams[] =
    {
        {"mf-video", MF_SOURCE_READER_FIRST_VIDEO_STREAM, &MFMediaType_Video, &MFVideoFormat_NV12, 30},
        {"mf-audio", MF_SOURCE_READER_FIRST_AUDIO_STREAM, &MFMediaType_Audio, &MFAudioFormat_PCM, 10},
    };
    IMFSourceReader *reader = NULL;
    char detail[200];
    HRESULT hr = MFCreateSourceReaderFromURL(file, NULL, &reader);
    unsigned int i;

    for (i = 0; i < 2; i++)
    {
        IMFMediaType *type = NULL;
        HRESULT last = hr;
        LONGLONG end = 0;
        int n = -1;
        if (SUCCEEDED(hr)) last = MFCreateMediaType(&type);
        if (SUCCEEDED(last)) last = IMFMediaType_SetGUID(type, &MF_MT_MAJOR_TYPE, streams[i].major);
        if (SUCCEEDED(last)) last = IMFMediaType_SetGUID(type, &MF_MT_SUBTYPE, streams[i].subtype);
        if (SUCCEEDED(last)) last = IMFSourceReader_SetStreamSelection(reader, MF_SOURCE_READER_ALL_STREAMS, FALSE);
        if (SUCCEEDED(last)) last = IMFSourceReader_SetStreamSelection(reader, streams[i].stream, TRUE);
        if (SUCCEEDED(last)) last = IMFSourceReader_SetCurrentMediaType(reader, streams[i].stream, NULL, type);
        if (SUCCEEDED(last))
        {
            PROPVARIANT pos;
            PropVariantInit(&pos);
            pos.vt = VT_I8;
            pos.hVal.QuadPart = 0;
            if (i) IMFSourceReader_SetCurrentPosition(reader, &GUID_NULL, &pos);
            n = read_stream(reader, streams[i].stream, &last, &end);
        }
        if (type) IMFMediaType_Release(type);
        if (n >= 0)
            snprintf(detail, sizeof(detail), "%d samples decoded, the last at %.2f s", n, end / 1e7);
        else
            snprintf(detail, sizeof(detail), "failed: 0x%08lx", (unsigned long)last);
        report(streams[i].name, n >= streams[i].least, detail);
    }
    if (reader) IMFSourceReader_Release(reader);
}

typedef HRESULT (WINAPI *create_sync_reader_fn)(IUnknown *, DWORD, IWMSyncReader **);

static void check_wm(const WCHAR *file)
{
    HMODULE wmvcore = LoadLibraryA("wmvcore.dll");
    create_sync_reader_fn create = wmvcore ? (create_sync_reader_fn)(void *)GetProcAddress(wmvcore, "WMCreateSyncReader") : NULL;
    IWMSyncReader *reader = NULL;
    int video = -1, audio = -1, counts[8] = {0};
    DWORD outputs = 0, i;
    char detail[200];
    HRESULT hr = create ? create(NULL, 0, &reader) : E_NOTIMPL;

    if (SUCCEEDED(hr)) hr = IWMSyncReader_Open(reader, file);
    if (SUCCEEDED(hr)) hr = IWMSyncReader_GetOutputCount(reader, &outputs);
    for (i = 0; SUCCEEDED(hr) && i < outputs && i < 8; i++)
    {
        IWMOutputMediaProps *props = NULL;
        GUID major;
        if (SUCCEEDED(IWMSyncReader_GetOutputProps(reader, i, &props)) && SUCCEEDED(IWMOutputMediaProps_GetType(props, &major)))
        {
            if (IsEqualGUID(&major, &WMMEDIATYPE_Video)) video = i;
            if (IsEqualGUID(&major, &WMMEDIATYPE_Audio)) audio = i;
        }
        if (props) IWMOutputMediaProps_Release(props);
    }
    while (SUCCEEDED(hr))
    {
        INSSBuffer *sample = NULL;
        QWORD time = 0, duration = 0;
        DWORD flags = 0, output = 0;
        WORD stream = 0;
        hr = IWMSyncReader_GetNextSample(reader, 0, &sample, &time, &duration, &flags, &output, &stream);
        if (hr == NS_E_NO_MORE_SAMPLES) break;
        if (SUCCEEDED(hr) && sample)
        {
            if (output < 8) counts[output]++;
            INSSBuffer_Release(sample);
        }
    }
    if (hr == NS_E_NO_MORE_SAMPLES) hr = S_OK;
    snprintf(detail, sizeof(detail), "%d frames decoded (%lu outputs; status 0x%08lx)",
             video >= 0 ? counts[video] : 0, (unsigned long)outputs, (unsigned long)hr);
    report("wm-video", SUCCEEDED(hr) && video >= 0 && counts[video] >= 30, detail);
    snprintf(detail, sizeof(detail), "%d audio buffers decoded (status 0x%08lx)", audio >= 0 ? counts[audio] : 0, (unsigned long)hr);
    report("wm-audio", SUCCEEDED(hr) && audio >= 0 && counts[audio] >= 10, detail);
    if (reader)
    {
        IWMSyncReader_Close(reader);
        IWMSyncReader_Release(reader);
    }
}

int wmain(int argc, WCHAR **argv)
{
    if (argc < 2)
    {
        printf("usage: mediaprobe FILE\n");
        return 2;
    }
    CoInitializeEx(NULL, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION, MFSTARTUP_FULL);
    check_mf(argv[1]);
    check_wm(argv[1]);
    MFShutdown();
    CoUninitialize();
    printf("done\t%d\n", failures);
    fflush(stdout);
    return failures;
}
