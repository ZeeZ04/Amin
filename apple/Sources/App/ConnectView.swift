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
    .background(Color.aminBg.ignoresSafeArea())
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
    VStack(spacing: AminSpace.xl) {
      DoorPanel {
        DoorMark(tint: .aminOnDoor).frame(width: 80, height: 80)
          .padding(.top, 48).padding(.bottom, AminSpace.xl)
      }
      .frame(maxWidth: 240)
      VStack(spacing: AminSpace.sm) {
        Text("Your Amin computer").font(.aminSerif(.title, weight: .semibold)).foregroundStyle(Color.aminInk)
          .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        Text("Amin runs on a computer in your home. When your documents hold the answer, it shows you the passage.")
          .font(.aminBody).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }
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
        Text("Password").font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminMuted)
        SecureField("6 or more characters", text: $password)
          .textContentType(creating ? .newPassword : .password)
          .aminField()
      }
      if firstAccount {
        Label("This is the first account on this Amin computer. It becomes the admin, who invites everyone else.",
              systemImage: "person.badge.key")
          .font(.callout).foregroundStyle(.secondary)
      }
      if creating && !firstAccount {
        field("Invite code", text: $invite, prompt: "From the person who runs Amin", hint: nil)
      }

      let ready = !(working || address.isEmpty || name.isEmpty || password.count < 6)
      Button(action: go) {
        HStack(spacing: AminSpace.sm) {
          if working { LanternDot(size: 10) }
          Text(creating ? "Create account" : "Sign in").font(.aminHeadline)
        }
        .frame(maxWidth: .infinity, minHeight: 52)
        .foregroundStyle(ready ? Color.aminOnAccent : Color.aminMuted)
        .background(ready ? Color.aminAccent : Color.aminLine.opacity(0.6), in: RoundedRectangle(cornerRadius: AminRadius.md))
      }
      .buttonStyle(.plain)
      .disabled(!ready)
      if !ready && !working {
        Text(address.isEmpty ? "Enter your Amin computer's address." : name.isEmpty ? "Enter your name on that computer."
             : "Passwords are 6 or more characters.")
          .font(.aminCaption).foregroundStyle(Color.aminMuted).frame(maxWidth: .infinity)
      }

      if let error { Text(error).font(.callout).foregroundStyle(.red) }

      Label("Nothing you ask or upload leaves your Amin computer.", systemImage: "lock")
        .font(.footnote).foregroundStyle(.secondary)

      #if os(iOS) || os(macOS) || os(visionOS)
      Button { choosingModel = true } label: {
        HStack(alignment: .top, spacing: AminSpace.md) {
          Image(systemName: "cpu").font(.title3).foregroundStyle(Color.aminAccentInk)
            .frame(width: 40, height: 40).background(Color.aminAccentWash, in: RoundedRectangle(cornerRadius: AminRadius.sm))
          VStack(alignment: .leading, spacing: AminSpace.xs) {
            Text("Run Amin on this device only").font(.aminHeadline).foregroundStyle(Color.aminInk)
            Text("Choose the edge-2 model folder. Answers come from the model here, with no network.")
              .font(.aminCaption).foregroundStyle(Color.aminMuted).fixedSize(horizontal: false, vertical: true)
          }
          Spacer(minLength: 0)
        }
        .padding(AminSpace.lg)
        .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.lg))
        .overlay(RoundedRectangle(cornerRadius: AminRadius.lg).strokeBorder(Color.aminLine))
      }
      .buttonStyle(.plain)
      .padding(.top, AminSpace.sm)
      .fileImporter(isPresented: $choosingModel, allowedContentTypes: [.folder]) { result in
        do { try model.useLocalModel(at: result.get()) } catch { self.error = error.localizedDescription }
      }
      #endif
    }
  }

  private func field(_ title: String, text: Binding<String>, prompt: String, hint: String?) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title).font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminMuted)
      TextField(prompt, text: text)
        .aminField()
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
