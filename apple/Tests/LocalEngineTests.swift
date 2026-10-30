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
    let engine = LocalEngine(directory: Self.model, library: nil)
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
    let a = try await LocalEngine(directory: Self.model, library: nil).ask("When does my tenancy agreement end?", project: nil, conversation: nil)
    print("decline →", a.text.prefix(160))
    #expect(!a.text.contains("2026") && !a.text.contains("2027"), "must not invent a date")
  }

  @Test(.enabled(if: FileManager.default.fileExists(atPath: model.appending(path: "config.json").path())))
  func `answers from a document on this device and cites it`() async throws {
    let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let lib = try LocalLibrary(url: dir.appending(path: "lib.db"))
    let f = dir.appending(path: "tenancy.md")
    try "# Tenancy\nThe tenancy at 14 Elm Road runs from 1 March 2026 to 28 February 2027. Rent is 950 pounds a month, due on the 1st."
      .write(to: f, atomically: true, encoding: .utf8)
    try lib.add(f)
    let engine = LocalEngine(directory: Self.model, library: lib)
    for q in ["When does my tenancy end?", "എന്റെ വാടക എത്രയാണ്?"] {
      let a = try await engine.ask(q, project: nil, conversation: nil)
      print("doc Q:", q, "→", a.text, a.citationOrder, "(\(a.latencyMs) ms)")
      if q.hasPrefix("When") {
        #expect(a.basis == "documents" && a.text.contains("2027"))
        #expect(a.citationOrder.first?.hasPrefix("p.tenancy.md#") == true)
      }
    }
    let off = try await engine.ask("What is my car's registration number?", project: nil, conversation: nil)
    print("not in docs →", off.basis, off.text.prefix(140))
    #expect(off.basis == "general" && off.citationOrder.isEmpty)
  }
}

struct WakePhraseTests {
  @Test(arguments: ["Hey Amin", "hey ameen what's the time", "Hi, Amine", "OK amen", "hey a man"])
  func `wakes on the name after a greeting`(_ heard: String) { #expect(WakePhrase.matches(heard)) }

  @Test(arguments: ["Amina called earlier", "Hey, I mean it", "Hey Siri", "the amenity fee", "hey amina"])
  func `stays quiet otherwise`(_ heard: String) { #expect(!WakePhrase.matches(heard)) }
}
