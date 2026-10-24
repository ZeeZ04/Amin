import SwiftUI

enum Destination: Hashable {
  case chat, documents, projects, settings
  case conversation(String)
}

/// Sidebar + detail. On iPad, Mac and Vision Pro both show; on iPhone and
/// Apple TV the split view collapses to a stack automatically.
struct MainView: View {
  #if os(tvOS)
  var body: some View { PhoneTabs() }
  #else
  @Environment(\.horizontalSizeClass) private var size

  var body: some View {
    // iPhone: tabs, like the web app's phone layout. Wider screens: a sidebar.
    if size == .compact { PhoneTabs() } else { SplitLayout() }
  }
  #endif
}

/// Tabs for iPhone and Apple TV; each tab owns its navigation stack.
struct PhoneTabs: View {
  @Environment(AppModel.self) private var model
  @State private var tab = "chat"

  var body: some View {
    TabView(selection: $tab) {
      Tab("Chat", systemImage: "bubble.left.and.text.bubble.right", value: "chat") {
        NavigationStack { ChatView(showsHistory: true) }
      }
      Tab("Documents", systemImage: "doc.badge.plus", value: "documents") {
        NavigationStack { DocumentsView() }
      }
      Tab("Projects", systemImage: "folder", value: "projects") {
        NavigationStack { ProjectsView(onAsk: { pid in model.newChat(in: pid); tab = "chat" }) }
      }
      Tab("Settings", systemImage: "gearshape", value: "settings") {
        NavigationStack { SettingsView() }
      }
    }
    .errorAlert()
  }
}

struct SplitLayout: View {
  @Environment(AppModel.self) private var model
  @State private var selection: Destination? = .chat

  var body: some View {
    NavigationSplitView {
      Sidebar(selection: $selection)
        #if os(macOS)
        .navigationSplitViewColumnWidth(min: 220, ideal: 260)
        #endif
    } detail: {
      NavigationStack {
        switch selection ?? .chat {
        case .chat, .conversation: ChatView()
        case .documents: DocumentsView()
        case .projects: ProjectsView(onAsk: { pid in model.newChat(in: pid); selection = .chat })
        case .settings: SettingsView()
        }
      }
    }
    .onChange(of: selection) { _, new in
      if case .conversation(let id) = new { Task { await model.open(id) } }
    }
    .errorAlert()
  }
}

/// Recent conversations as a sheet: the iPhone's way into history.
struct HistorySheet: View {
  @Environment(AppModel.self) private var model
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    NavigationStack {
      List {
        if model.conversations.isEmpty {
          ContentUnavailableView("No conversations yet", systemImage: "clock",
                                 description: Text("Your conversations will appear here."))
        }
        ForEach(model.conversations) { c in
          Button {
            Task { await model.open(c.id); dismiss() }
          } label: {
            VStack(alignment: .leading, spacing: 2) {
              Text(c.title).lineLimit(1).foregroundStyle(.primary)
              Text(Date(timeIntervalSince1970: c.updated), format: .relative(presentation: .named))
                .font(.caption).foregroundStyle(.secondary)
            }
          }
          #if !os(tvOS)
          .swipeActions { Button("Delete", systemImage: "trash", role: .destructive) { Task { await model.delete(c.id) } } }
          #endif
        }
      }
      .navigationTitle("History")
      .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
    }
  }
}

extension View {
  func errorAlert() -> some View { modifier(ErrorAlert()) }
}

private struct ErrorAlert: ViewModifier {
  @Environment(AppModel.self) private var model
  func body(content: Content) -> some View {
    content.alert("Something went wrong", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
      Button("OK", role: .cancel) {}
    } message: { Text(model.error ?? "") }
  }
}

struct Sidebar: View {
  @Environment(AppModel.self) private var model
  @Binding var selection: Destination?

  var body: some View {
    List(selection: $selection) {
      Section {
        Button {
          model.newChat(); selection = .chat
        } label: { Label("New chat", systemImage: "square.and.pencil") }
        NavigationLink(value: Destination.chat) { Label("Chat", systemImage: "bubble.left.and.text.bubble.right") }
        NavigationLink(value: Destination.documents) { Label("Documents", systemImage: "doc.badge.plus") }
        NavigationLink(value: Destination.projects) { Label("Projects", systemImage: "folder") }
        NavigationLink(value: Destination.settings) { Label("Settings", systemImage: "gearshape") }
      }
      Section("Recent") {
        if model.conversations.isEmpty {
          Text("Your conversations will appear here.").font(.callout).foregroundStyle(.secondary)
        }
        ForEach(model.conversations) { c in
          NavigationLink(value: Destination.conversation(c.id)) {
            VStack(alignment: .leading, spacing: 2) {
              Text(c.title).lineLimit(1)
              Text(Date(timeIntervalSince1970: c.updated), format: .relative(presentation: .named))
                .font(.caption).foregroundStyle(.secondary)
            }
          }
          .contextMenu {
            Button("Delete", systemImage: "trash", role: .destructive) { Task { await model.delete(c.id) } }
          }
          #if !os(tvOS)
          .swipeActions {
            Button("Delete", systemImage: "trash", role: .destructive) { Task { await model.delete(c.id) } }
          }
          #endif
        }
      }
    }
    .navigationTitle("Amin")
    .refreshable { try? await model.refresh() }
  }
}
