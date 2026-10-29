import Foundation
import Testing

/// Runs Amin's own model through the same LocalEngine the app uses (needs the
/// edge-2 weights on disk; skipped otherwise). MLX needs real hardware, so
/// this runs on the Mac, not in the iOS Simulator.
struct LocalEngineTests {
  nonisolated static let model = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    .appending(path: "data/models/edge-2-q6")

  @Test(.enabled(if: FileManager.default.fileExists(atPath: model.appending(path: "config.json").path())))
  func `answers on device in three languages`() async throws {
    let engine = LocalEngine(directory: Self.model)
    for (q, mustContain) in [("What is the capital of Japan?", "Tokyo"),
                             ("ما هي عاصمة اليابان؟", "طوكيو"),
                             ("ജപ്പാന്റെ തലസ്ഥാനം ഏതാണ്?", "ടോക്കിയോ")] {
      let a = try await engine.ask(q, project: nil, conversation: nil)
      print("Q:", q, "→", a.text.prefix(120), "(\(a.latencyMs) ms)")
      #expect(a.basis == "general")
      #expect(a.text.contains(mustContain))
    }
  }

  @Test(.enabled(if: FileManager.default.fileExists(atPath: model.appending(path: "config.json").path())))
  func `declines personal details it cannot know`() async throws {
    let a = try await LocalEngine(directory: Self.model).ask("When does my tenancy agreement end?", project: nil, conversation: nil)
    print("decline →", a.text.prefix(160))
    #expect(!a.text.contains("2026") && !a.text.contains("2027"), "must not invent a date")
  }
}
