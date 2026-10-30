#if os(iOS) || os(macOS) || os(visionOS)
import Foundation
import Observation

/// Copies Amin's own model into this app's storage (ADR-014), from the Amin
/// computer on the home network or from Hugging Face (ModelSource). A file
/// already present at full size is skipped, so an interrupted download
/// resumes where it stopped.
@Observable
final class ModelDownloader {
  enum State: Equatable { case idle, downloading(Double), done(URL), failed(String) }
  private(set) var state: State = .idle

  static var root: URL {
    URL.applicationSupportDirectory.appending(path: "Models", directoryHint: .isDirectory)
  }

  /// Which model suits this device: iPhones get about 6 GB, so the 4-bit mix; Macs and iPads the 6-bit build.
  static func recommended(from models: [ModelInfo]) -> ModelInfo? {
    #if os(iOS)
    let order = UIDeviceIsPad ? ["edge-2-q6", "edge-2-m46"] : ["edge-2-m46"]
    #else
    let order = ["edge-2-q6", "edge-2-q8", "edge-2-m46"]
    #endif
    return order.lazy.compactMap { n in models.first { $0.name == n } }.first
  }

  func download(_ info: ModelInfo, from source: any ModelSource) async {
    let dir = Self.root.appending(path: info.name, directoryHint: .isDirectory)
    do {
      try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
      var done: Int64 = 0
      state = .downloading(0)
      for f in info.files {
        let dest = dir.appending(path: f.name)
        if let size = try? dest.resourceValues(forKeys: [.fileSizeKey]).fileSize, Int64(size) == f.bytes {
          done += f.bytes; state = .downloading(Double(done) / Double(max(info.bytes, 1))); continue
        }
        let before = done, total = Double(max(info.bytes, 1))
        let tmp = try await source.modelFile(info.name, f.name) { written in
          Task { @MainActor in self.state = .downloading(Double(before + written) / total) }
        }
        try? FileManager.default.removeItem(at: dest)
        try FileManager.default.moveItem(at: tmp, to: dest)
        done += f.bytes
        state = .downloading(Double(done) / Double(max(info.bytes, 1)))
      }
      // Keep the model out of iCloud backups: it is large and can be fetched again at home.
      var values = URLResourceValues(); values.isExcludedFromBackup = true
      var d = dir; try? d.setResourceValues(values)
      state = .done(dir)
    } catch {
      state = .failed(error.localizedDescription)
    }
  }
}

#if os(iOS)
import UIKit
private var UIDeviceIsPad: Bool { UIDevice.current.userInterfaceIdiom == .pad }
#endif
#endif
