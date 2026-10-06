// make-sample.swift OUT.mp4 -- writes the playback gate's sample: one second of 64x64 H.264 video
// (30 frames of a moving gradient) and AAC audio (a quiet 440 Hz tone, 44.1 kHz mono), in an MP4,
// with Apple's own encoders (AVFoundation). The sample is committed (tools/media/sample.mp4), so a
// build never depends on an encoder; this script shows how it was made.
//
//   xcrun swift tools/media/make-sample.swift tools/media/sample.mp4
import AVFoundation
import CoreMedia
import CoreVideo
import Foundation

let out = URL(fileURLWithPath: CommandLine.arguments[1])
try? FileManager.default.removeItem(at: out)
let writer = try AVAssetWriter(outputURL: out, fileType: .mp4)

let size = 64, frames = 30, rate: Int32 = 30
let video = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: size, AVVideoHeightKey: size,
    AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 200_000, AVVideoMaxKeyFrameIntervalKey: 30,
                                      AVVideoProfileLevelKey: AVVideoProfileLevelH264MainAutoLevel],
])
video.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: video, sourcePixelBufferAttributes: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
    kCVPixelBufferWidthKey as String: size, kCVPixelBufferHeightKey as String: size,
])
let sampleRate = 44100.0
let audio = AVAssetWriterInput(mediaType: .audio, outputSettings: [
    AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: 1,
    AVEncoderBitRateKey: 64000,
])
audio.expectsMediaDataInRealTime = false
writer.add(video)
writer.add(audio)
guard writer.startWriting() else { fatalError("startWriting: \(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)

for i in 0..<frames {
    while !video.isReadyForMoreMediaData { usleep(1000) }
    var pb: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &pb)
    let buffer = pb!
    CVPixelBufferLockBaseAddress(buffer, [])
    let base = CVPixelBufferGetBaseAddress(buffer)!.assumingMemoryBound(to: UInt8.self)
    let stride = CVPixelBufferGetBytesPerRow(buffer)
    for y in 0..<size {
        for x in 0..<size {
            let p = base + y * stride + x * 4
            p[0] = UInt8((x * 4 + i * 8) & 255)  // B
            p[1] = UInt8((y * 4) & 255)          // G
            p[2] = UInt8((i * 8) & 255)          // R
            p[3] = 255
        }
    }
    CVPixelBufferUnlockBaseAddress(buffer, [])
    adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(i), timescale: rate))
}
video.markAsFinished()

// Audio: 1 s of 16-bit PCM in blocks of 1024 frames.
var asbd = AudioStreamBasicDescription(mSampleRate: sampleRate, mFormatID: kAudioFormatLinearPCM,
                                       mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
                                       mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2,
                                       mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0)
var format: CMAudioFormatDescription?
CMAudioFormatDescriptionCreate(allocator: nil, asbd: &asbd, layoutSize: 0, layout: nil, magicCookieSize: 0,
                               magicCookie: nil, extensions: nil, formatDescriptionOut: &format)
let total = Int(sampleRate), block = 1024
var done = 0
while done < total {
    let n = min(block, total - done)
    var pcm = [Int16](repeating: 0, count: n)
    for k in 0..<n { pcm[k] = Int16(2000 * sin(2 * Double.pi * 440 * Double(done + k) / sampleRate)) }
    var blockBuffer: CMBlockBuffer?
    CMBlockBufferCreateWithMemoryBlock(allocator: nil, memoryBlock: nil, blockLength: n * 2, blockAllocator: nil,
                                       customBlockSource: nil, offsetToData: 0, dataLength: n * 2, flags: 0,
                                       blockBufferOut: &blockBuffer)
    _ = pcm.withUnsafeBytes { CMBlockBufferReplaceDataBytes(with: $0.baseAddress!, blockBuffer: blockBuffer!, offsetIntoDestination: 0, dataLength: n * 2) }
    var sample: CMSampleBuffer?
    CMAudioSampleBufferCreateReadyWithPacketDescriptions(allocator: nil, dataBuffer: blockBuffer!, formatDescription: format!,
                                                         sampleCount: n, presentationTimeStamp: CMTime(value: CMTimeValue(done), timescale: CMTimeScale(sampleRate)),
                                                         packetDescriptions: nil, sampleBufferOut: &sample)
    while !audio.isReadyForMoreMediaData { usleep(1000) }
    audio.append(sample!)
    done += n
}
audio.markAsFinished()

let finished = DispatchSemaphore(value: 0)
writer.finishWriting { finished.signal() }
finished.wait()
guard writer.status == .completed else { fatalError("finishWriting: \(String(describing: writer.error))") }
print("\(out.path): \((try? FileManager.default.attributesOfItem(atPath: out.path)[.size]) ?? 0) bytes")
