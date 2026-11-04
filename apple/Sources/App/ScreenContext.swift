#if os(macOS)
import AppKit
import ScreenCaptureKit
import Vision

/// One look at the window in front, taken only when the owner presses the
/// screen shortcut. It stays in memory and on this Mac: nothing is saved or sent.
struct ScreenContext {
  let appName: String
  let bundleID: String?
  let image: CGImage
  let text: String
  /// The window's frame in global display points, origin top-left (ScreenCaptureKit's space).
  let frame: CGRect
  /// Each line OCR read, with its box in Vision's space: 0...1, origin bottom-left.
  let lines: [Line]

  struct Line {
    let text: String
    let box: CGRect
  }

  /// Enough for an error and the code around it. The end of a window is kept
  /// over the middle, since terminals and consoles put the newest lines last.
  static let maxCharacters = 8000

  /// `scale` below the screen's own saves work when live help reads every few seconds.
  static let needsAccess = "Allow Amin under System Settings > Privacy & Security > Screen & System Audio Recording, quit and reopen Amin, then try again."

  /// CGPreflightScreenCaptureAccess can say no for a sandboxed app that has been allowed,
  /// so when it does, ask ScreenCaptureKit itself: listing windows only works with access.
  static func hasAccess() async -> Bool {
    if CGPreflightScreenCaptureAccess() { return true }
    return (try? await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)) != nil
  }

  static func capture(scale: CGFloat? = nil) async throws -> ScreenContext {
    guard await hasAccess() else {
      CGRequestScreenCaptureAccess()
      throw AminError.server(needsAccess)
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
    let scale = scale ?? NSScreen.main?.backingScaleFactor ?? 2
    config.width = Int(window.frame.width * scale)
    config.height = Int(window.frame.height * scale)
    let image = try await SCScreenshotManager.captureImage(
      contentFilter: SCContentFilter(desktopIndependentWindow: window), configuration: config)
    let lines = try await readText(image)
    let text = lines.map(\.text).joined(separator: "\n")
    guard !text.isEmpty else { throw AminError.server("Amin couldn't read any text in that window.") }
    return ScreenContext(appName: app.localizedName ?? "this app", bundleID: app.bundleIdentifier,
                         image: image, text: limited(text),
                         frame: window.frame, lines: lines)
  }

  /// ScreenCaptureKit doesn't promise an order, so ask the window server which is on top.
  private static func frontmost(of windows: [SCWindow]) -> SCWindow? {
    let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
    let order = (info as? [[String: Any]] ?? []).compactMap { $0[kCGWindowNumber as String] as? CGWindowID }
    return order.lazy.compactMap { id in windows.first { $0.windowID == id } }.first ?? windows.first
  }

  private static func readText(_ image: CGImage) async throws -> [Line] {
    try await Task.detached(priority: .userInitiated) {
      let request = VNRecognizeTextRequest()
      request.recognitionLevel = .accurate
      request.automaticallyDetectsLanguage = true
      request.usesLanguageCorrection = false  // correction "fixes" code into English
      try VNImageRequestHandler(cgImage: image).perform([request])
      return (request.results ?? []).compactMap { o in o.topCandidates(1).first.map { Line(text: $0.string, box: o.boundingBox) } }
    }.value
  }

  /// Where `line` is on screen, with the lines of its paragraph below it, in AppKit
  /// coordinates (origin bottom-left of the main screen). Nil when OCR can't place it.
  func region(of line: String) -> NSRect? {
    let probe = line.replacingOccurrences(of: "…", with: "").prefix(40)
    guard let i = lines.firstIndex(where: { $0.text.hasPrefix(probe) || line.hasPrefix($0.text) && $0.text.count > 10 })
    else { return nil }
    var box = lines[i].box
    var last = lines[i].box
    for next in lines.dropFirst(i + 1).prefix(8) {
      let gap = last.minY - next.box.maxY
      guard gap >= -0.002, gap < last.height * 1.3, abs(next.box.minX - box.minX) < 0.2 else { break }
      box = box.union(next.box)
      last = next.box
    }
    let top = frame.minY + (1 - box.maxY) * frame.height
    let rect = CGRect(x: frame.minX + box.minX * frame.width, y: top,
                      width: box.width * frame.width, height: box.height * frame.height)
    let mainHeight = NSScreen.screens.first?.frame.height ?? 0
    return NSRect(x: rect.minX, y: mainHeight - rect.maxY, width: rect.width, height: rect.height)
  }

  static func limited(_ text: String) -> String {
    guard text.count > maxCharacters else { return text }
    return "\(text.prefix(maxCharacters / 4))\n[...]\n\(text.suffix(maxCharacters * 3 / 4))"
  }
}
#endif
