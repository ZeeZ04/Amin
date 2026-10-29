import SwiftUI

/// First run: which Amin computer, then who you are.
struct ConnectView: View {
  @Environment(AppModel.self) private var model
  @State private var address = ""
  @State private var name = ""
  @State private var password = ""
  @State private var invite = ""
  @State private var creating = false
  @State private var firstAccount = false
  @State private var working = false
  @State private var error: String?
  @State private var choosingModel = false

  var body: some View {
    ScrollView {
      VStack(spacing: 28) {
        header
        form
      }
      .frame(maxWidth: 440)
      .padding(.horizontal, 24)
      .padding(.vertical, 40)
      .frame(maxWidth: .infinity)
    }
    .background(Color.aminTealDeep.opacity(0.04))
    .onAppear { address = model.serverURL?.absoluteString ?? "" }
    .task(id: address) {
      // Ask the server early whether this is its first account, which needs
      // no invite and becomes the admin: then the form can say so.
      try? await Task.sleep(for: .milliseconds(500))
      guard let client = try? model.connect(to: address), let s = try? await client.setup() else { return }
      firstAccount = s.firstAccount
      if firstAccount { creating = true }
    }
  }

  private var header: some View {
    VStack(spacing: 14) {
      DoorMark().frame(width: 72, height: 72)
      Text("Amin").font(.largeTitle.bold())
      Text("A private assistant that runs on your own computer. When your documents hold the answer, it shows you the passage.")
        .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
    }
  }

  private var form: some View {
    VStack(alignment: .leading, spacing: 16) {
      field("Amin computer", text: $address, prompt: "192.168.1.20:8000", hint: "The address make serve printed on your Mac.")
        #if os(iOS)
        .keyboardType(.URL)
        #endif

      Picker("Account", selection: $creating) {
        Text("Sign in").tag(false)
        Text("Create account").tag(true)
      }
      .pickerStyle(.segmented)
      .labelsHidden()

      field("Name", text: $name, prompt: "abdul", hint: creating ? "Lowercase letters, numbers, - or _." : nil)
        .textContentType(.username)
      VStack(alignment: .leading, spacing: 6) {
        Text("Password").font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
        SecureField("6 or more characters", text: $password)
          .textContentType(creating ? .newPassword : .password)
          .boxedField()
      }
      if firstAccount {
        Label("This is the first account on this Amin computer. It becomes the admin, who invites everyone else.",
              systemImage: "person.badge.key")
          .font(.callout).foregroundStyle(.secondary)
      }
      if creating && !firstAccount {
        field("Invite code", text: $invite, prompt: "From the person who runs Amin", hint: nil)
      }

      Button(action: go) {
        HStack { if working { ProgressView().controlSize(.small) }; Text(creating ? "Create account" : "Sign in") }
          .frame(maxWidth: .infinity, minHeight: 32)
      }
      .buttonStyle(.borderedProminent)
      .controlSize(.large)
      .disabled(working || address.isEmpty || name.isEmpty || password.count < 6)

      if let error { Text(error).font(.callout).foregroundStyle(.red) }

      Label("Nothing you ask or upload leaves your Amin computer.", systemImage: "lock")
        .font(.footnote).foregroundStyle(.secondary)

      #if os(iOS) || os(macOS) || os(visionOS)
      Divider().padding(.vertical, 6)
      VStack(alignment: .leading, spacing: 8) {
        Text("Or run Amin on this device only").font(.headline)
        Text("Choose the edge-2 model folder. Answers come from the model on this device, with no account and no network.")
          .font(.callout).foregroundStyle(.secondary)
        Button("Choose model folder", systemImage: "cpu") { choosingModel = true }
          .buttonStyle(.bordered)
      }
      .fileImporter(isPresented: $choosingModel, allowedContentTypes: [.folder]) { result in
        do { try model.useLocalModel(at: result.get()) } catch { self.error = error.localizedDescription }
      }
      #endif
    }
  }

  private func field(_ title: String, text: Binding<String>, prompt: String, hint: String?) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
      TextField(prompt, text: text)
        .boxedField()
        .autocorrectionDisabled()
        #if !os(macOS)
        .textInputAutocapitalization(.never)
        #endif
      if let hint { Text(hint).font(.caption).foregroundStyle(.secondary) }
    }
  }

  private func go() {
    working = true; error = nil
    Task {
      defer { working = false }
      do {
        let client = try model.connect(to: address)
        firstAccount = (try? await client.setup().firstAccount) ?? false
        let user = name.trimmingCharacters(in: .whitespaces).lowercased()
        if creating {
          try await client.signUp(name: user, password: password, invite: invite.isEmpty ? nil : invite)
        } else {
          try await client.signIn(name: user, password: password)
        }
        password = ""
        try await model.signedIn()
      } catch {
        self.error = error.localizedDescription
      }
    }
  }
}
