/* mediacheck: load the engine's GStreamer or FFmpeg the way Wine does and report what it finds.
 *
 *   mediacheck gst LIBGSTREAMER ELEMENT...
 *       Initialises GStreamer from that file, creates each element, then lists every plugin the
 *       registry holds with its declared licence and file. Lines: "element\tok|FAIL\tname" and
 *       "plugin\tname\tlicence\tfile". Exit status: the number of elements that failed.
 *   mediacheck ffmpeg LIBAVCODEC DECODER...
 *       Prints avcodec_license() and avcodec_configuration(), and finds each decoder.
 *
 * Uses dlsym only, so it needs no GStreamer or FFmpeg headers. */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

typedef struct list { void *data; struct list *next, *prev; } list;

static void *sym(void *h, const char *name)
{
    void *p = dlsym(h, name);
    if (!p) { fprintf(stderr, "missing symbol %s: %s\n", name, dlerror()); }
    return p;
}

static int gst(int argc, char **argv)
{
    void *h = dlopen(argv[2], RTLD_NOW | RTLD_GLOBAL);
    if (!h) { printf("load\tFAIL\t%s\n", dlerror()); return 100; }
    void (*init)(int *, char ***) = sym(h, "gst_init");
    void *(*make)(const char *, const char *) = sym(h, "gst_element_factory_make");
    void *(*registry_get)(void) = sym(h, "gst_registry_get");
    list *(*plugins)(void *) = sym(h, "gst_registry_get_plugin_list");
    const char *(*p_name)(void *) = sym(h, "gst_plugin_get_name");
    const char *(*p_license)(void *) = sym(h, "gst_plugin_get_license");
    const char *(*p_file)(void *) = sym(h, "gst_plugin_get_filename");
    char *(*version)(void) = sym(h, "gst_version_string");
    if (!init || !make || !registry_get || !plugins || !p_name || !p_license || !p_file || !version) return 101;
    init(NULL, NULL);
    printf("version\t%s\n", version());
    int failed = 0;
    for (int i = 3; i < argc; i++)
    {
        void *e = make(argv[i], NULL);
        printf("element\t%s\t%s\n", e ? "ok" : "FAIL", argv[i]);
        if (!e) failed++;
    }
    for (list *l = plugins(registry_get()); l; l = l->next)
    {
        const char *file = p_file(l->data);
        printf("plugin\t%s\t%s\t%s\n", p_name(l->data), p_license(l->data), file ? file : "(built in)");
    }
    fflush(stdout);
    return failed;
}

static int ffmpeg(int argc, char **argv)
{
    void *h = dlopen(argv[2], RTLD_NOW | RTLD_GLOBAL);
    if (!h) { printf("load\tFAIL\t%s\n", dlerror()); return 100; }
    const char *(*license)(void) = sym(h, "avcodec_license");
    const char *(*configuration)(void) = sym(h, "avcodec_configuration");
    void *(*find)(const char *) = sym(h, "avcodec_find_decoder_by_name");
    if (!license || !configuration || !find) return 101;
    printf("license\t%s\n", license());
    printf("configuration\t%s\n", configuration());
    int failed = 0;
    for (int i = 3; i < argc; i++)
    {
        void *d = find(argv[i]);
        printf("decoder\t%s\t%s\n", d ? "ok" : "FAIL", argv[i]);
        if (!d) failed++;
    }
    fflush(stdout);
    return failed;
}

int main(int argc, char **argv)
{
    if (argc >= 3 && !strcmp(argv[1], "gst")) return gst(argc, argv);
    if (argc >= 3 && !strcmp(argv[1], "ffmpeg")) return ffmpeg(argc, argv);
    fprintf(stderr, "usage: mediacheck gst|ffmpeg LIBRARY NAME...\n");
    return 2;
}
