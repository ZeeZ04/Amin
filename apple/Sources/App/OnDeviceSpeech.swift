#if os(iOS) || os(macOS) || os(visionOS)
import Foundation
import Speech

/// Speech to text with no server: Apple's on-device recogniser
/// (requiresOnDeviceRecognition, so audio never leaves the device). It covers
/// English and Arabic. Malayalam has no on-device Apple model, so Malayalam
/// speech needs the Amin computer's Whisper (amin/voice.py) until WhisperKit
/// lands (docs/team/RESEARCH.md).
/// `nonisolated`: Speech and TCC call back on their own queues; under the app's
/// main-actor default these closures would assert on the main queue and trap.
nonisolated enum OnDeviceSpeech {
  static func transcribe(_ file: URL) async -> String? {
    guard await authorised() else { return nil }
    for id in preferredLocales() {
      guard let r = SFSpeechRecognizer(locale: Locale(identifier: id)), r.isAvailable, r.supportsOnDeviceRecognition
      else { continue }
      let req = SFSpeechURLRecognitionRequest(url: file)
      req.requiresOnDeviceRecognition = true
      req.shouldReportPartialResults = false
      if let text = await recognise(r, req), !text.isEmpty { return text }
    }
    return nil
  }

  /// The device language first, then English and Arabic.
  private static func preferredLocales() -> [String] {
    var ids = [Locale.preferredLanguages.first ?? "en-US", "en-US", "ar-SA"]
    var seen = Set<String>()
    ids = ids.filter { seen.insert($0).inserted }
    return ids
  }

  static func authorised() async -> Bool {
    await withCheckedContinuation { cont in
      SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0 == .authorized) }
    }
  }

  private static func recognise(_ r: SFSpeechRecognizer, _ req: SFSpeechURLRecognitionRequest) async -> String? {
    await withCheckedContinuation { cont in
      var done = false
      r.recognitionTask(with: req) { result, error in
        guard !done else { return }
        if let result, result.isFinal { done = true; cont.resume(returning: result.bestTranscription.formattedString) }
        else if error != nil { done = true; cont.resume(returning: nil) }
      }
    }
  }
}
#endif
