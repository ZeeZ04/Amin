import SwiftUI

@main
struct AminApp: App {
  @State private var model = AppModel()
  #if os(iOS)
  @State private var relay: RelayServer?
  #endif

  var body: some Scene {
    #if os(macOS)
    main
      .defaultSize(width: 1100, height: 760)
      .commands {
        CommandGroup(replacing: .newItem) {
          Button("New Chat") { model.newChat() }.keyboardShortcut("n")
        }
        CommandGroup(after: .windowArrangement) {
          AmbientCommand()
          Button("Quick Ask") { QuickAsk.shared.show() }
        }
      }
    // The JARVIS-style ambient display: put it on a big screen and say "Hey Amin".
    Window("Amin Ambient", id: "ambient") {
      AmbientView().environment(model)
    }
    .windowStyle(.hiddenTitleBar)
    .defaultSize(width: 1280, height: 800)
    // Quick ask from anywhere: the menu-bar door, or the shortcut chosen in Settings.
    MenuBarExtra("Amin", systemImage: "door.left.hand.open") { QuickAskMenu() }
    #else
    main
    #endif
  }

  private var main: some Scene {
    WindowGroup(id: "main") {
      RootView()
        .environment(model)
        #if os(iOS) || os(macOS) || os(visionOS)
        .onOpenURL { url in  // amin://auth-callback from a confirmation or reset email
          Task {
            await model.account.handle(url)
            if model.account.isSignedIn { await model.accountSignedIn() }
          }
        }
        #endif
        .tint(.aminTeal)
        .task {
          await model.resume()
          #if os(macOS)
          QuickAsk.shared.install(model: model)
          #endif
          #if os(iOS)
          // The Watch asks through this phone, with this phone's sign-in.
          let model = model
          relay = RelayServer(engine: { MainActor.assumeIsolated { model.client } })
          #endif
        }
    }
  }
}

#if os(macOS)
struct AmbientCommand: View {
  @Environment(\.openWindow) private var openWindow
  var body: some View {
    Button("Ambient Mode") { openWindow(id: "ambient") }.keyboardShortcut("a", modifiers: [.command, .shift])
  }
}
#endif

struct RootView: View {
  @Environment(AppModel.self) private var model
  @AppStorage("amin.onboarded") private var onboarded = false

  var body: some View {
    switch model.phase {
    case .connect:
      #if os(iOS) || os(macOS) || os(visionOS)
      if model.account.isConfigured { AuthView() } else { ConnectView() }
      #else
      ConnectView()
      #endif
    case .ready:
      if onboarded { MainView() } else { OnboardingView(done: $onboarded) }
    }
  }
}
