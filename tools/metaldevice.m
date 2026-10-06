/* metaldevice: prints the name of this machine's default Metal device and exits 0, or prints nothing
 * and exits 1 when there is none. Built for x86_64, so it sees Metal as DXMT does under Rosetta. The
 * d3d11 gate runs it first: a machine without Metal (GitHub's Intel runners are virtual machines
 * without one) cannot run DXMT, and the gate reports SKIP there instead of a failure. */
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>

int main(void)
{
    @autoreleasepool
    {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) return 1;
        printf("%s\n", [[device name] UTF8String]);
    }
    return 0;
}
