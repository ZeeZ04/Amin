import SwiftUI

enum Destination: Hashable {
  case chat, documents, projects, settings
  case conversation(String)
}

/// Sidebar + detail. On iPad, Mac and Vision Pro both show; on iPhone and
/// Apple TV the split view collapses to a stack automatically.
struct MainView: View {
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
    .alert("Something went wrong", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
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
