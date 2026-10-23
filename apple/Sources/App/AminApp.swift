import SwiftUI

@main
struct AminApp: App {
  @State private var model = AppModel()
  #if os(iOS)
  @State private var relay: RelayServer?
  #endif

  var body: some Scene {
    WindowGroup {
      RootView()
        .environment(model)
        .tint(.aminTeal)
        .task {
          await model.resume()
          #if os(iOS)
          // The Watch asks through this phone, with this phone's sign-in.
          let model = model
          relay = RelayServer(engine: { MainActor.assumeIsolated { model.client } })
          #endif
        }
    }
    #if os(macOS)
    .defaultSize(width: 1100, height: 760)
    .commands {
      CommandGroup(replacing: .newItem) {
        Button("New Chat") { model.newChat() }.keyboardShortcut("n")
      }
    }
    #endif
  }
}

struct RootView: View {
  @Environment(AppModel.self) private var model

  var body: some View {
    switch model.phase {
    case .connect: ConnectView()
    case .ready: MainView()
    }
  }
}
