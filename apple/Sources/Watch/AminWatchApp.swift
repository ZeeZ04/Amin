import SwiftUI

/// Apple Watch: ask by dictation, answered through the paired iPhone.
@main
struct AminWatchApp: App {
  var body: some Scene {
    WindowGroup { WatchAsk() }
  }
}

struct WatchAsk: View {
  @State private var relay = RelayClient()
  @State private var question = ""
  @State private var answer: (text: String, general: Bool)?
  @State private var error: String?
  @State private var working = false

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 10) {
        HStack {
          DoorMark(tint: .aminSand).frame(width: 22, height: 22)
          Text("Amin").font(.headline)
        }
        TextField("Ask Amin", text: $question)
          .onSubmit(ask)
        if working { ProgressView() }
        if let answer {
          Text(answer.general ? "General knowledge" : "From your documents")
            .font(.caption2).foregroundStyle(answer.general ? .secondary : Color.aminSaffron)
          Text(answer.text).font(.body)
        }
        if let error { Text(error).font(.footnote).foregroundStyle(.red) }
      }
    }
    .containerBackground(Color.aminTealDeep.gradient, for: .navigation)
  }

  private func ask() {
    let q = question.trimmingCharacters(in: .whitespaces)
    guard !q.isEmpty else { return }
    working = true; error = nil; answer = nil
    Task {
      defer { working = false }
      do { answer = try await relay.ask(q) } catch { self.error = error.localizedDescription }
    }
  }
}
