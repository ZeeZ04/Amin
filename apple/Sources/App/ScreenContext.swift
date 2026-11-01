#if os(macOS)
import AppKit
import ScreenCaptureKit
import Vision

/// One look at the window in front, taken only when the owner presses the
/// screen shortcut. It stays in memory and on this Mac: nothing is saved or sent.
struct ScreenContext {
  let appName: String
  let image: CGImage
  let text: String

  /// Enough for an error and the code around it. The end of a window is kept
  /// over the middle, since terminals and consoles put the newest lines last.
  static let maxCharacters = 8000

  static func capture() async throws -> ScreenContext {
    guard CGPreflightScreenCaptureAccess() else {
      CGRequestScreenCaptureAccess()
      throw AminError.server("Allow Amin under System Settings > Privacy & Security > Screen Recording, reopen Amin, then try again.")
    }
    guard let app = NSWorkspace.shared.frontmostApplication,
          app.processIdentifier != ProcessInfo.processInfo.processIdentifier else {
      throw AminError.server("Click the window you want Amin to read, then press the shortcut again.")
    }
    let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
    let windows = content.windows.filter {
      $0.owningApplication?.processID == app.processIdentifier && $0.windowLayer == 0 && $0.frame.height > 80
    }
    guard let window = frontmost(of: windows) else {
      throw AminError.server("Amin couldn't find a window to read in \(app.localizedName ?? "that app").")
    }
    let config = SCStreamConfiguration()
    let scale = NSScreen.main?.backingScaleFactor ?? 2
    config.width = Int(window.frame.width * scale)
    config.height = Int(window.frame.height * scale)
    let image = try await SCScreenshotManager.captureImage(
      contentFilter: SCContentFilter(desktopIndependentWindow: window), configuration: config)
    let text = try await readText(image)
    guard !text.isEmpty else { throw AminError.server("Amin couldn't read any text in that window.") }
    return ScreenContext(appName: app.localizedName ?? "this app", image: image, text: limited(text))
  }

  /// ScreenCaptureKit doesn't promise an order, so ask the window server which is on top.
  private static func frontmost(of windows: [SCWindow]) -> SCWindow? {
    let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
    let order = (info as? [[String: Any]] ?? []).compactMap { $0[kCGWindowNumber as String] as? CGWindowID }
    return order.lazy.compactMap { id in windows.first { $0.windowID == id } }.first ?? windows.first
  }

  private static func readText(_ image: CGImage) async throws -> String {
    try await Task.detached(priority: .userInitiated) {
      let request = VNRecognizeTextRequest()
      request.recognitionLevel = .accurate
      request.automaticallyDetectsLanguage = true
      request.usesLanguageCorrection = false  // correction "fixes" code into English
      try VNImageRequestHandler(cgImage: image).perform([request])
      return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    }.value
  }

  static func limited(_ text: String) -> String {
    guard text.count > maxCharacters else { return text }
    return "\(text.prefix(maxCharacters / 4))\n[...]\n\(text.suffix(maxCharacters * 3 / 4))"
  }
}
#endif
