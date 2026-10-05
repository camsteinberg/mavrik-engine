/* dlcheck: dlopen each file named on the command line, in one process, and report.
 * Exit status: the number of files that failed to load (0 means all loaded). */
#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    int failed = 0;
    for (int i = 1; i < argc; i++)
    {
        void *h = dlopen(argv[i], RTLD_NOW | RTLD_LOCAL);
        if (h) printf("ok\t%s\n", argv[i]);
        else
        {
            printf("FAIL\t%s\t%s\n", argv[i], dlerror());
            failed++;
        }
    }
    fflush(stdout);
    return failed > 125 ? 125 : failed;
}
