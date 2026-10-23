import SwiftUI

struct SettingsView: View {
  @Environment(AppModel.self) private var model
  @State private var invite: String?
  @State private var confirmSignOut = false

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

        Section("General chat may use") {
          Toggle("My library", isOn: prefBinding(\.chatPrivate))
          Toggle("Household library", isOn: prefBinding(\.chatHousehold))
        }
      }

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
    .confirmationDialog("Sign out of Amin on this device?", isPresented: $confirmSignOut, titleVisibility: .visible) {
      Button("Sign out", role: .destructive) { Task { await model.signOut() } }
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
