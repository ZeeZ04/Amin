import AppIntents
import Foundation

/// "Hey Siri, ask Amin" — the only background wake word iPhone and Watch
/// allow belongs to Siri, so this is how Amin is reached hands-free there.
/// Siri asks "What do you want to ask?", then Amin answers out loud.
struct AskAminIntent: AppIntent {
  static let title: LocalizedStringResource = "Ask Amin"
  static let description = IntentDescription("Ask Amin a question. It answers from your documents when they hold the answer.")
  static let openAppWhenRun = false

  @Parameter(title: "Question", requestValueDialog: "What do you want to ask?")
  var question: String

  func perform() async throws -> some IntentResult & ProvidesDialog & ReturnsValue<String> {
    guard let saved = UserDefaults.standard.string(forKey: AppModel.serverKey), let url = URL(string: saved) else {
      throw AminError.server("Open Amin once and connect to your Amin computer first.")
    }
    let answer = try await AminClient(base: url).ask(question, project: nil, conversation: nil)
    let spoken = answer.isGeneral ? answer.text : (answer.claims.isEmpty ? answer.text : "From your documents: \(answer.text)")
    return .result(value: answer.text, dialog: IntentDialog(stringLiteral: spoken))
  }
}

struct AminShortcuts: AppShortcutsProvider {
  static var appShortcuts: [AppShortcut] {
    AppShortcut(intent: AskAminIntent(),
                phrases: ["Ask \(.applicationName)", "Ask \(.applicationName) a question", "Hey \(.applicationName)"],
                shortTitle: "Ask Amin",
                systemImageName: "bubble.left.and.text.bubble.right")
  }
}
