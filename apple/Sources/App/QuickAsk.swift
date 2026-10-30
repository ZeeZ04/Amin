#if os(macOS)
import AppKit
import Carbon.HIToolbox
import SwiftUI

/// The shortcut that opens quick ask from any app. ⌥Space is taken by Gemini,
/// ChatGPT/Codex and Claude on many Macs, so Amin defaults to ⌥⇧Space and the
/// owner picks another in Settings.
enum QuickAskShortcut: String, CaseIterable, Identifiable {
  case optionShiftSpace, controlOptionSpace, optionShiftA, controlSpace, off
  var id: String { rawValue }
  static let key = "amin.quickAskShortcut"
  static var current: QuickAskShortcut {
    UserDefaults.standard.string(forKey: key).flatMap(Self.init(rawValue:)) ?? .optionShiftSpace
  }
  var label: String {
    switch self {
    case .optionShiftSpace: "⌥⇧Space"
    case .controlOptionSpace: "⌃⌥Space"
    case .optionShiftA: "⌥⇧A"
    case .controlSpace: "⌃Space (replaces the input-source switch)"
    case .off: "Off"
    }
  }
  /// Carbon key code and modifiers, or nil when off.
  var carbon: (key: UInt32, mods: UInt32)? {
    switch self {
    case .optionShiftSpace: (UInt32(kVK_Space), UInt32(optionKey | shiftKey))
    case .controlOptionSpace: (UInt32(kVK_Space), UInt32(controlKey | optionKey))
    case .optionShiftA: (UInt32(kVK_ANSI_A), UInt32(optionKey | shiftKey))
    case .controlSpace: (UInt32(kVK_Space), UInt32(controlKey))
    case .off: nil
    }
  }
}

/// The Mac quick-ask panel (docs/team/D3, DESIGN.md §3): a shortcut from any app
/// opens a floating field; the answer appears below with its sources. The
/// hotkey uses Carbon's RegisterEventHotKey, which needs no accessibility
/// permission. Questions go into the current conversation, so ⌘⏎ continues
/// in the main window.
final class QuickAsk {
  static let shared = QuickAsk()
  private var panel: NSPanel?
  private var hotKey: EventHotKeyRef?
  private var model: AppModel?

  private var handlerInstalled = false

  func install(model: AppModel) {
    self.model = model
    if !handlerInstalled {
      var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
      InstallEventHandler(GetApplicationEventTarget(), quickAskHotKeyPressed, 1, &spec, nil, nil)
      handlerInstalled = true
    }
    apply(QuickAskShortcut.current)
  }

  /// Swap the global shortcut; the old one is released first.
  func apply(_ shortcut: QuickAskShortcut) {
    UserDefaults.standard.set(shortcut.rawValue, forKey: QuickAskShortcut.key)
    if let hotKey { UnregisterEventHotKey(hotKey); self.hotKey = nil }
    guard let c = shortcut.carbon else { return }
    let id = EventHotKeyID(signature: OSType(0x414D_494E), id: 1)  // 'AMIN'
    RegisterEventHotKey(c.key, c.mods, id, GetApplicationEventTarget(), 0, &hotKey)
  }

  func toggle() {
    if let panel, panel.isVisible { hide() } else { show() }
  }

  func show() {
    guard let model else { return }
    let panel = panel ?? makePanel(model: model)
    self.panel = panel
    if let screen = NSScreen.main?.visibleFrame {
      // Centred, in the upper third of the screen.
      panel.setFrameTopLeftPoint(NSPoint(x: screen.midX - 320, y: screen.maxY - screen.height / 4))
    }
    panel.makeKeyAndOrderFront(nil)
  }

  func hide() { panel?.orderOut(nil) }

  /// ⌘⏎: bring the main window forward, where the exchange already is.
  func continueInMainWindow() {
    hide()
    NSApp.activate()
    NSApp.windows.first { $0.identifier?.rawValue.hasPrefix("main") == true }?.makeKeyAndOrderFront(nil)
  }

  private func makePanel(model: AppModel) -> NSPanel {
    let panel = KeyPanel(contentRect: NSRect(x: 0, y: 0, width: 640, height: 80),
                         styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView],
                         backing: .buffered, defer: true)
    panel.isFloatingPanel = true
    panel.level = .floating
    panel.hidesOnDeactivate = false
    panel.titleVisibility = .hidden
    panel.titlebarAppearsTransparent = true
    panel.isMovableByWindowBackground = true
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
    panel.backgroundColor = .clear
    let host = NSHostingView(rootView: QuickAskView().environment(model).tint(.aminTeal))
    host.sizingOptions = [.preferredContentSize]
    panel.contentView = host
    return panel
  }
}

/// A non-activating panel still has to take keystrokes for its field.
private final class KeyPanel: NSPanel {
  override var canBecomeKey: Bool { true }
}

/// Carbon calls this on the main thread; it cannot carry actor isolation itself.
nonisolated private func quickAskHotKeyPressed(_: EventHandlerCallRef?, _: EventRef?, _: UnsafeMutableRawPointer?) -> OSStatus {
  MainActor.assumeIsolated { QuickAsk.shared.toggle() }
  return noErr
}

struct QuickAskView: View {
  @Environment(AppModel.self) private var model
  @State private var question = ""
  @State private var answer: Answer?
  @State private var asked = ""
  @FocusState private var focused: Bool

  init(answer: Answer? = nil) { _answer = State(initialValue: answer) }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: AminSpace.md) {
        DoorMark().frame(width: 22, height: 22)
        TextField("Ask Amin", text: $question)
          .textFieldStyle(.plain)
          .font(.system(size: 22))
          .focused($focused)
          .onSubmit(ask)
        if model.isBusy { ProgressView().controlSize(.small) }
      }
      .padding(AminSpace.lg)

      if let answer {
        Divider()
        ScrollView {
          VStack(alignment: .leading, spacing: AminSpace.md) {
            Text(answer.text)
              .font(.aminAnswer)
              .foregroundStyle(Color.aminInk)
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: AminSpace.sm) {
              Label(source(answer), systemImage: answer.isGeneral ? "sparkles" : "doc.text")
                .font(.aminCaption).foregroundStyle(Color.aminMuted)
              Spacer()
              Button("Copy", systemImage: "doc.on.doc") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(answer.text, forType: .string)
              }
              .keyboardShortcut("c", modifiers: [.command, .shift])
              Button("Continue in Amin", systemImage: "arrow.up.right.square") { QuickAsk.shared.continueInMainWindow() }
                .keyboardShortcut(.return, modifiers: .command)
            }
            .buttonStyle(.borderless)
          }
          .padding(AminSpace.lg)
        }
        .frame(maxHeight: 360)
        .fixedSize(horizontal: false, vertical: true)
      } else if model.engine == nil {
        Divider()
        Text("Connect to your Amin computer or choose a model on this Mac first.")
          .font(.aminCaption).foregroundStyle(Color.aminMuted).padding(AminSpace.lg)
      }
    }
    .frame(width: 640)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: AminRadius.xl))
    .onExitCommand { QuickAsk.shared.hide() }
    .onAppear { focused = true }
  }

  private func source(_ a: Answer) -> String {
    if a.isGeneral { return "General knowledge, not from your documents" }
    let n = a.citationOrder.count
    return "From your documents · \(n) source\(n == 1 ? "" : "s")"
  }

  private func ask() {
    let q = question.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !q.isEmpty else { return }
    asked = q
    question = ""
    Task { answer = await model.ask(q) }
  }
}

#Preview("Quick ask, answered") {
  QuickAskView(answer: Answer(
    question: "What is the warranty?", outcome: "answered", basis: "documents",
    claims: [Claim(text: "The ArcticLine FR-440 has a 24-month warranty; the sealed cooling system is covered for 60 months.",
                   citations: ["h.fridge-manual#001-ab"], verdict: "supported")],
    latencyMs: 900))
  .environment(AppModel())
}

/// The menu-bar door: quick ask, the app, and ambient mode.
struct QuickAskMenu: View {
  @Environment(\.openWindow) private var openWindow
  var body: some View {
    Button("Quick Ask   \(QuickAskShortcut.current.label)") { QuickAsk.shared.show() }
    Button("Open Amin") { NSApp.activate(); openWindow(id: "main") }
    Button("Ambient Mode") { NSApp.activate(); openWindow(id: "ambient") }
    Divider()
    Button("Quit Amin") { NSApp.terminate(nil) }.keyboardShortcut("q")
  }
}
#endif
