import SwiftUI

struct SettingsView: View {
  @Environment(AppModel.self) private var model
  @State private var invite: String?
  @State private var facts: [Fact] = []
  @State private var newFact = ""
  @State private var confirmSignOut = false
  @State private var choosingModel = false
  @State private var preferLocal = true

  var body: some View {
    Form {
      if let me = model.me {
        Section {
          HStack(spacing: 14) {
            Text(me.name.prefix(1).uppercased())
              .font(.title2.bold()).foregroundStyle(.white)
              .frame(width: 52, height: 52).background(Color.aminTeal, in: Circle())
            VStack(alignment: .leading) {
              Text(me.name).font(.headline)
              Text(me.admin ? "Admin · can invite people" : "Household member").font(.subheadline).foregroundStyle(.secondary)
            }
          }
        }

        if me.admin {
          Section {
            Button("Create an invite code", systemImage: "person.badge.plus") {
              Task { invite = try? await model.client?.invite().code }
            }
            if let invite {
              LabeledContent("Code") { Text(invite).font(.title3.monospaced().bold()).selectable() }
            }
          } header: { Text("Invite someone") } footer: { Text("One use, valid for 7 days.") }
        }

        Section {
          HStack {
            TextField("Teach Amin something", text: $newFact)
              .onSubmit(teach)
            Button("Remember", action: teach).disabled(newFact.trimmingCharacters(in: .whitespaces).isEmpty)
          }
          ForEach(facts.reversed()) { f in
            VStack(alignment: .leading, spacing: 2) {
              Text(f.text)
              Text(Date(timeIntervalSince1970: f.created), format: .dateTime.day().month().year())
                .font(.caption).foregroundStyle(.secondary)
            }
            .contextMenu { Button("Forget", systemImage: "trash", role: .destructive) { forget(f) } }
            #if !os(tvOS)
            .swipeActions { Button("Forget", systemImage: "trash", role: .destructive) { forget(f) } }
            #endif
          }
        } header: { Text("Memory") } footer: {
          Text("You can also say “Remember that …” in chat. Facts stay on your Amin computer and are cited like documents. Forget one and Amin stops using it at once.")
        }

        Section("General chat may use") {
          Toggle("My library", isOn: prefBinding(\.chatPrivate))
          Toggle("Household library", isOn: prefBinding(\.chatHousehold))
        }
      }

      #if os(iOS) || os(macOS) || os(visionOS)
      Section {
        if let name = model.localModelName {
          LabeledContent("Model", value: name)
          if model.serverURL != nil {
            Toggle("Answer on this device", isOn: $preferLocal)
              .onChange(of: preferLocal) { _, v in model.preferLocal = v }
          }
          Button("Remove model", role: .destructive) { model.forgetLocalModel() }
        } else {
          Button("Choose model folder", systemImage: "cpu") { choosingModel = true }
        }
      } header: { Text("On this device") } footer: {
        Text("Amin's own model (edge-2) runs here, so nothing you ask leaves this device. Answers from your documents still come from your Amin computer.")
      }
      .fileImporter(isPresented: $choosingModel, allowedContentTypes: [.folder]) { result in
        do { try model.useLocalModel(at: result.get()) } catch { model.error = error.localizedDescription }
      }
      .onAppear { preferLocal = model.preferLocal }
      #endif

      Section("Amin computer") {
        LabeledContent("Address", value: model.serverURL?.absoluteString ?? "—")
        Button("Sign out", role: .destructive) { confirmSignOut = true }
      }

      Section {
        Text("Amin runs on your own computer. Questions, documents and conversations stay there. When your documents hold the answer, Amin quotes them and shows the passage; otherwise it answers from general knowledge and says so.")
          .font(.callout).foregroundStyle(.secondary)
      } header: { Text("About") }
    }
    .navigationTitle("Settings")
    .task { facts = (try? await model.client?.memory()) ?? [] }
    .confirmationDialog("Sign out of Amin on this device?", isPresented: $confirmSignOut, titleVisibility: .visible) {
      Button("Sign out", role: .destructive) { Task { await model.signOut() } }
    }
  }

  private func teach() {
    let text = newFact.trimmingCharacters(in: .whitespaces)
    guard !text.isEmpty else { return }
    newFact = ""
    Task {
      do { _ = try await model.client?.remember(text); facts = (try? await model.client?.memory()) ?? facts }
      catch { model.error = error.localizedDescription }
    }
  }

  private func forget(_ f: Fact) {
    Task {
      try? await model.client?.forget(f.id)
      facts.removeAll { $0.id == f.id }
    }
  }

  private func prefBinding(_ key: WritableKeyPath<Prefs, Bool>) -> Binding<Bool> {
    Binding(
      get: { model.me?.prefs[keyPath: key] ?? false },
      set: { value in
        guard var prefs = model.me?.prefs else { return }
        prefs[keyPath: key] = value
        Task {
          _ = try? await model.client?.setPrefs(prefs)
          try? await model.refresh()
        }
      })
  }
}
