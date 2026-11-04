#if os(macOS)
import AppKit
import SwiftUI

/// Live help: while it is on, Amin reads the front window every few seconds. When
/// it finds a coding error, task or question, it outlines it on the window and
/// writes the steps and the answer in a panel beside it. Off by default. The
/// menu-bar icon shows an eye while it watches. Captures stay in memory on this
/// Mac, and only the found question and nearby text reach the local model.
@MainActor @Observable
final class LiveHelp {
  static let shared = LiveHelp()
  static let key = "amin.liveHelp"

  struct Card {
    let found: LiveDetector.Found
    let appName: String
    /// The reply so far, then the whole reply.
    var reply = ""
    var done = false
    var failed: String?
    var parsed: LiveAnswer { LiveAnswer(reply) }
  }

  private(set) var isOn = false
  private(set) var status = ""
  private(set) var card: Card?
  private var loop: Task<Void, Never>?
  private var model: AppModel?
  private let overlay = LiveOverlay()
  private var control: NSPanel?
  /// Found on the last look but not yet answered: it must still be there next time,
  /// so a half-typed line or a scrolling log isn't answered.
  private var pending: LiveDetector.Found?
  private var answered: [String] = []
  /// Where the answered question's window was; the overlay goes when the window moves.
  private var answeredFrame: CGRect?

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
    Task {
      guard await ScreenContext.hasAccess() else {
        CGRequestScreenCaptureAccess()
        status = ScreenContext.needsAccess
        showControl()
        return
      }
      begin()
    }
  }

  private func begin() {
    UserDefaults.standard.set(true, forKey: Self.key)
    isOn = true
    status = "Watching the front window"
    showControl()
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
    dismiss()
    control?.orderOut(nil)
  }

  func dismiss() {
    card = nil
    answeredFrame = nil
    overlay.hide()
  }

  private func look() async {
    guard card?.done ?? true else { return }  // one answer at a time
    guard let screen = try? await ScreenContext.capture(),
          !Self.neverRead.contains(screen.bundleID ?? "") else { return }
    if let answeredFrame, card != nil, screen.frame != answeredFrame { dismiss() }  // moved, or another window
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
    card = Card(found: found, appName: screen.appName)
    answeredFrame = screen.frame
    overlay.show(question: screen.region(of: found.line), window: screen.frame, live: self)
    let task = switch found.kind {
    case .error: "Explain this error and fix it: \(found.line)"
    case .task: "Solve this coding task, using the details shown on screen: \(found.line)"
    case .question: found.line
    }
    let question = """
      \(task)

      Reply in exactly this format:
      Steps:
      1. <one short step>
      2. <one short step>
      Answer:
      <the final answer. For code, the complete code in one code block, in the language asked for (Python if none).>
      """
    do {
      _ = try await local.askAboutScreen(
        question, appName: screen.appName, screenText: screen.text, maxTokens: found.kind == .task ? 1500 : 900,
        onText: { text in await MainActor.run { LiveHelp.shared.card?.reply = text } })
      card?.done = true
    } catch {
      card?.failed = error.localizedDescription
      card?.done = true
    }
  }

  /// The small on/off control in the top-right corner.
  private func showControl() {
    let panel = control ?? LiveOverlay.panel(LiveControlView(live: self), interactive: true)
    control = panel
    if let screen = NSScreen.main?.visibleFrame {
      panel.setFrameTopLeftPoint(NSPoint(x: screen.maxX - 330, y: screen.maxY - 12))
    }
    panel.orderFrontRegardless()
  }
}

/// Draws on the window: an outline round the question, and the steps and answer beside it.
@MainActor
final class LiveOverlay {
  private var outline: NSPanel?
  private var answer: NSPanel?
  private var top = NSPoint.zero
  static let width: CGFloat = 470

  func show(question: NSRect?, window: CGRect, live: LiveHelp) {
    hide()
    let screen = NSScreen.main?.visibleFrame ?? .zero
    let mainHeight = NSScreen.screens.first?.frame.height ?? 0
    let windowRect = NSRect(x: window.minX, y: mainHeight - window.maxY, width: window.width, height: window.height)
    let anchor = question ?? NSRect(x: windowRect.minX + 40, y: windowRect.maxY - 120, width: 10, height: 10)
    if let question {
      let ring = question.insetBy(dx: -8, dy: -6)
      let o = Self.panel(OutlineView(), interactive: false)
      o.setFrame(ring, display: true)
      o.orderFrontRegardless()
      outline = o
    }
    // Beside the question if it fits, then on its left, then below it.
    let w = Self.width, gap: CGFloat = 18
    var x = anchor.maxX + gap
    if x + w > screen.maxX { x = anchor.minX - gap - w }
    var y = anchor.maxY
    if x < screen.minX {
      x = min(max(anchor.minX, screen.minX + 8), screen.maxX - w - 8)
      y = anchor.minY - gap
    }
    top = NSPoint(x: x, y: min(max(y, screen.minY + 200), screen.maxY - 8))
    let a = Self.panel(LiveAnswerView(live: live, maxHeight: min(screen.height * 0.75, 720)) { [weak self] in
      self?.keepTop()
    }, interactive: true)
    a.setFrameTopLeftPoint(top)
    a.orderFrontRegardless()
    answer = a
  }

  /// The panel grows as the answer is written; keep its top edge where it started.
  func keepTop() { answer?.setFrameTopLeftPoint(top) }

  func hide() {
    outline?.orderOut(nil)
    answer?.orderOut(nil)
    outline = nil
    answer = nil
  }

  static func panel(_ view: some View, interactive: Bool) -> NSPanel {
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 300, height: 100),
                        styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: true)
    panel.isFloatingPanel = true
    panel.level = .floating
    panel.hidesOnDeactivate = false
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    panel.backgroundColor = .clear
    panel.hasShadow = interactive
    panel.ignoresMouseEvents = !interactive
    let host = NSHostingView(rootView: view.tint(.aminTeal))
    if interactive { host.sizingOptions = [.preferredContentSize] }
    panel.contentView = host
    return panel
  }
}

private struct OutlineView: View {
  var body: some View {
    RoundedRectangle(cornerRadius: 8)
      .strokeBorder(Color.aminTeal, lineWidth: 3)
      .background(Color.aminTeal.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
  }
}

struct LiveControlView: View {
  let live: LiveHelp

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.xs) {
      HStack(spacing: AminSpace.sm) {
        Image(systemName: live.isOn ? "eye" : "eye.slash")
        Text(live.isOn ? "Live help is on" : "Live help is off").font(.aminCaption.bold())
        Spacer()
        Button(live.isOn ? "Stop" : "Start") { live.toggle() }.buttonStyle(.borderless)
      }
      if !live.status.isEmpty, !live.isOn || live.card == nil {
        Text(live.status).font(.aminCaption).foregroundStyle(Color.aminMuted)
      }
    }
    .foregroundStyle(Color.aminInk)
    .padding(AminSpace.md)
    .frame(width: 318)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: AminRadius.lg))
  }
}

/// The steps and the answer, written beside the question.
private struct LiveAnswerView: View {
  let live: LiveHelp
  let maxHeight: CGFloat
  let resized: () -> Void

  var body: some View {
    if let card = live.card {
      let parsed = card.parsed
      VStack(alignment: .leading, spacing: AminSpace.md) {
        HStack(alignment: .top, spacing: AminSpace.sm) {
          Image(systemName: icon(card.found.kind)).foregroundStyle(Color.aminTeal)
          Text(card.found.line).font(.system(size: 14, weight: .semibold)).lineLimit(3)
          Spacer()
          Button("Close", systemImage: "xmark") { live.dismiss() }.labelStyle(.iconOnly).buttonStyle(.borderless)
        }
        ScrollView {
          VStack(alignment: .leading, spacing: AminSpace.md) {
            if !parsed.steps.isEmpty {
              Text("Steps").font(.system(size: 13, weight: .bold)).foregroundStyle(Color.aminMuted)
              ForEach(Array(parsed.steps.enumerated()), id: \.offset) { i, step in
                HStack(alignment: .firstTextBaseline, spacing: AminSpace.sm) {
                  Text("\(i + 1)").font(.system(size: 13, weight: .bold)).foregroundStyle(Color.aminOnAccent)
                    .frame(width: 22, height: 22).background(Color.aminTeal, in: Circle())
                  Text(step).font(.system(size: 15)).fixedSize(horizontal: false, vertical: true)
                }
              }
            }
            if !parsed.answer.isEmpty {
              Text("Answer").font(.system(size: 13, weight: .bold)).foregroundStyle(Color.aminMuted)
              Text(parsed.answer)
                .font(parsed.isCode ? .system(size: 14, design: .monospaced) : .system(size: 15))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(parsed.isCode ? AminSpace.md : 0)
                .background(parsed.isCode ? Color.aminInk.opacity(0.06) : .clear,
                            in: RoundedRectangle(cornerRadius: AminRadius.sm))
            }
            if let failed = card.failed {
              Text(failed).font(.aminCaption).foregroundStyle(Color.aminMuted)
            } else if !card.done {
              HStack(spacing: AminSpace.sm) {
                ProgressView().controlSize(.small)
                Text(card.reply.isEmpty ? "Reading the question…" : "Writing…")
                  .font(.aminCaption).foregroundStyle(Color.aminMuted)
              }
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxHeight: maxHeight)
        .fixedSize(horizontal: false, vertical: true)
        if card.done, card.failed == nil {
          HStack {
            Text("Seen in \(card.appName) · check the code before you use it")
              .font(.aminCaption).foregroundStyle(Color.aminMuted)
            Spacer()
            Button(parsed.isCode ? "Copy code" : "Copy", systemImage: "doc.on.doc") {
              NSPasteboard.general.clearContents()
              NSPasteboard.general.setString(parsed.isCode ? parsed.answer : card.reply, forType: .string)
            }
            .buttonStyle(.borderless)
          }
        }
      }
      .foregroundStyle(Color.aminInk)
      .padding(AminSpace.lg)
      .frame(width: LiveOverlay.width)
      .background(.regularMaterial, in: RoundedRectangle(cornerRadius: AminRadius.lg))
      .overlay(RoundedRectangle(cornerRadius: AminRadius.lg).strokeBorder(Color.aminTeal.opacity(0.5), lineWidth: 1.5))
      .onGeometryChange(for: CGSize.self) { $0.size } action: { _ in DispatchQueue.main.async(execute: resized) }
    }
  }

  private func icon(_ kind: LiveDetector.Found.Kind) -> String {
    switch kind {
    case .error: "exclamationmark.triangle"
    case .task: "chevron.left.forwardslash.chevron.right"
    case .question: "questionmark.circle"
    }
  }
}
#endif
