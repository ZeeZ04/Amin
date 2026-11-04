#if os(macOS)
import AppKit
import SwiftUI

/// Live help: while it is on, Amin reads the front window every few seconds and
/// answers coding errors and questions in a card in the top-right corner. Off by
/// default. The menu-bar icon shows an eye while it watches. Captures stay in
/// memory on this Mac, and only the found question and nearby text reach the
/// local model.
@MainActor @Observable
final class LiveHelp {
  static let shared = LiveHelp()
  static let key = "amin.liveHelp"

  struct Card: Identifiable {
    let id = UUID()
    let found: LiveDetector.Found
    let appName: String
    var answer: String?
    /// The answer while it is still being written.
    var draft = ""
    var failed: String?
  }

  private(set) var isOn = false
  private(set) var status = ""
  private(set) var cards: [Card] = []
  private var loop: Task<Void, Never>?
  private var panel: NSPanel?
  private var model: AppModel?
  /// Found on the last look but not yet answered: it must still be there next time,
  /// so a half-typed line or a scrolling log isn't answered.
  private var pending: LiveDetector.Found?
  private var answered: [String] = []

  /// Password managers and system security screens are never read.
  static let neverRead: Set<String> = [
    "com.1password.1password", "com.agilebits.onepassword7", "com.bitwarden.desktop", "com.apple.keychainaccess",
    "com.apple.Passwords", "com.apple.systempreferences", "com.apple.SecurityAgent", "com.lastpass.LastPass",
    "com.dashlane.dashlanephonefinal",
  ]

  func install(model: AppModel) {
    self.model = model
    if UserDefaults.standard.bool(forKey: Self.key) { start() }
  }

  func toggle() { isOn ? stop() : start() }

  func start() {
    guard CGPreflightScreenCaptureAccess() else {
      CGRequestScreenCaptureAccess()
      status = "Allow Amin under System Settings > Privacy & Security > Screen Recording, then reopen Amin."
      showPanel()
      return
    }
    UserDefaults.standard.set(true, forKey: Self.key)
    isOn = true
    status = "Watching the front window"
    showPanel()
    loop?.cancel()
    loop = Task { [weak self] in
      while !Task.isCancelled {
        await self?.look()
        try? await Task.sleep(for: .seconds(3))
      }
    }
  }

  func stop() {
    UserDefaults.standard.set(false, forKey: Self.key)
    isOn = false
    loop?.cancel()
    loop = nil
    pending = nil
    status = ""
    if cards.isEmpty { panel?.orderOut(nil) }
  }

  func dismiss(_ card: Card) {
    cards.removeAll { $0.id == card.id }
    if cards.isEmpty, !isOn { panel?.orderOut(nil) }
  }

  private func look() async {
    guard cards.allSatisfy({ $0.answer != nil || $0.failed != nil }) else { return }  // one answer at a time
    guard let screen = try? await ScreenContext.capture(scale: 1),
          !Self.neverRead.contains(screen.bundleID ?? "") else { return }
    guard let found = LiveDetector.find(in: screen.text), !answered.contains(found.key) else {
      pending = nil
      return
    }
    guard pending?.key == found.key else { pending = found; return }
    pending = nil
    answered = Array((answered + [found.key]).suffix(50))
    await answer(found, screen: screen)
  }

  private func answer(_ found: LiveDetector.Found, screen: ScreenContext) async {
    guard let local = model?.local as? LocalEngine else {
      status = "Choose a model on this Mac first. Screen text never leaves this Mac."
      return
    }
    let card = Card(found: found, appName: screen.appName)
    cards.insert(card, at: 0)
    cards = Array(cards.prefix(3))
    showPanel()
    let question = switch found.kind {
    case .error: "Explain this error briefly and give the fix: \(found.line)"
    case .task: """
      Solve this coding task, using the details shown on screen: \(found.line)
      Write the complete code first, in one code block, in the language the task asks for (Python if it doesn't say). \
      Then explain it in two or three short lines.
      """
    case .question: found.line
    }
    let id = card.id
    do {
      let a = try await local.askAboutScreen(
        question, appName: screen.appName, screenText: screen.text, maxTokens: found.kind == .task ? 1500 : 800,
        onText: { text in await MainActor.run { LiveHelp.shared.update(id) { $0.draft = text } } })
      update(card.id) { $0.answer = a.text }
    } catch {
      update(card.id) { $0.failed = error.localizedDescription }
    }
  }

  fileprivate func update(_ id: UUID, _ change: (inout Card) -> Void) {
    if let i = cards.firstIndex(where: { $0.id == id }) { change(&cards[i]) }
  }

  private func showPanel() {
    let panel = panel ?? makePanel()
    self.panel = panel
    if let screen = NSScreen.main?.visibleFrame {
      panel.setFrameTopLeftPoint(NSPoint(x: screen.maxX - 400, y: screen.maxY - 12))
    }
    panel.orderFrontRegardless()
  }

  private func makePanel() -> NSPanel {
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 388, height: 120),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: true)
    panel.isFloatingPanel = true
    panel.level = .floating
    panel.hidesOnDeactivate = false
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    panel.backgroundColor = .clear
    panel.hasShadow = true
    let host = NSHostingView(rootView: LiveHelpView(live: self).tint(.aminTeal))
    host.sizingOptions = [.preferredContentSize]
    panel.contentView = host
    return panel
  }
}

struct LiveHelpView: View {
  let live: LiveHelp

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.sm) {
      HStack(spacing: AminSpace.sm) {
        Image(systemName: live.isOn ? "eye" : "eye.slash")
        Text(live.isOn ? "Live help is on" : "Live help is off").font(.aminCaption.bold())
        Spacer()
        Button(live.isOn ? "Stop" : "Start") { live.toggle() }.buttonStyle(.borderless)
      }
      .foregroundStyle(Color.aminInk)
      if !live.status.isEmpty, live.cards.isEmpty {
        Text(live.status).font(.aminCaption).foregroundStyle(Color.aminMuted)
      }
      ForEach(live.cards) { card in LiveCardView(card: card) { live.dismiss(card) } }
    }
    .padding(AminSpace.md)
    .frame(width: 388)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: AminRadius.lg))
  }
}

private struct LiveCardView: View {
  let card: LiveHelp.Card
  let dismiss: () -> Void

  private var icon: String {
    switch card.found.kind {
    case .error: "exclamationmark.triangle"
    case .task: "chevron.left.forwardslash.chevron.right"
    case .question: "questionmark.circle"
    }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.xs) {
      HStack(alignment: .top) {
        Label(card.found.line, systemImage: icon)
          .font(.aminCaption.bold()).foregroundStyle(Color.aminInk).lineLimit(2)
        Spacer()
        Button("Dismiss", systemImage: "xmark") { dismiss() }.labelStyle(.iconOnly).buttonStyle(.borderless)
      }
      Text("Seen in \(card.appName)").font(.aminCaption).foregroundStyle(Color.aminMuted)
      if let answer = card.answer {
        ScrollView {
          Text(answer).font(card.found.kind == .task ? .system(.caption, design: .monospaced) : .aminCaption)
            .foregroundStyle(Color.aminInk).textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxHeight: card.found.kind == .task ? 320 : 220)
        Button("Copy", systemImage: "doc.on.doc") {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(answer, forType: .string)
        }
        .buttonStyle(.borderless).font(.aminCaption)
      } else if let failed = card.failed {
        Text(failed).font(.aminCaption).foregroundStyle(Color.aminMuted)
      } else if !card.draft.isEmpty {
        ScrollView {
          Text(card.draft).font(.system(.caption, design: .monospaced)).foregroundStyle(Color.aminInk)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .defaultScrollAnchor(.bottom)
        .frame(maxHeight: 320)
      } else {
        HStack(spacing: AminSpace.sm) {
          ProgressView().controlSize(.small)
          Text(card.found.kind == .task ? "Writing the code…" : "Thinking…").font(.aminCaption).foregroundStyle(Color.aminMuted)
        }
      }
    }
    .padding(AminSpace.sm)
    .background(Color.aminInk.opacity(0.05), in: RoundedRectangle(cornerRadius: AminRadius.md))
  }
}
#endif
