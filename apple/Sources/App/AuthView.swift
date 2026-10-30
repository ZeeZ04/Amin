#if os(iOS) || os(macOS) || os(visionOS)
import SwiftUI

/// Sign in or create an Amin account (Supabase). The account holds the plan
/// only; the promise on this screen is that nothing you ask goes with it.
/// People with an Amin computer at home can connect to it instead.
struct AuthView: View {
  @Environment(AppModel.self) private var model
  @State private var creating = true
  @State private var name = ""
  @State private var email = ""
  @State private var password = ""
  @State private var working = false
  @State private var error: String?
  @State private var notice: String?
  @State private var connecting = false
  @FocusState private var focus: Field?
  enum Field { case name, email, password }

  private var account: Account { model.account }

  var body: some View {
    ScrollView {
      VStack(spacing: AminSpace.xxl) {
        header
        if case .needsConfirmation(let address) = account.status {
          confirm(address)
        } else {
          form
        }
        footer
      }
      .frame(maxWidth: 420)
      .padding(.horizontal, AminSpace.xl)
      .padding(.vertical, AminSpace.huge)
      .frame(maxWidth: .infinity)
    }
    .scrollDismissesKeyboard(.interactively)
    .background(backdrop.ignoresSafeArea())
    .sheet(isPresented: $connecting) { NavigationStack { ConnectView().toolbar { closeButton } } }
    .animation(AminMotion.spring, value: creating)
  }

  private var backdrop: some View {
    ZStack {
      Color.aminBg
      RadialGradient(colors: [Color.aminAccent.opacity(0.16), .clear], center: .top, startRadius: 0, endRadius: 520)
    }
  }

  private var header: some View {
    VStack(spacing: AminSpace.lg) {
      DoorMark().frame(width: 84, height: 84)
        .shadow(color: Color.aminAccent.opacity(0.25), radius: 18, y: 8)
      Text(creating ? "Create your Amin account" : "Welcome back")
        .font(.amin(.largeTitle, weight: .bold)).multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
      Text("Your account holds your plan, nothing else. What you ask and the documents you add stay on this device.")
        .font(.aminBody).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var form: some View {
    VStack(alignment: .leading, spacing: AminSpace.lg) {
      Picker("", selection: $creating) {
        Text("Create account").tag(true)
        Text("Sign in").tag(false)
      }
      .pickerStyle(.segmented).labelsHidden()

      if creating {
        field("Name", text: $name, prompt: "What should Amin call you?", focus: .name)
          .textContentType(.name)
      }
      field("Email", text: $email, prompt: "you@example.com", focus: .email)
        .textContentType(.emailAddress)
        #if os(iOS)
        .keyboardType(.emailAddress)
        #endif
      VStack(alignment: .leading, spacing: AminSpace.xs) {
        Text("Password").font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminMuted)
        SecureField(creating ? "8 or more characters, with a number" : "Your password", text: $password)
          .textContentType(creating ? .newPassword : .password)
          .focused($focus, equals: .password)
          .onSubmit(go)
          .boxedField()
      }

      Button(action: go) {
        HStack(spacing: AminSpace.sm) {
          if working { ProgressView().controlSize(.small) }
          Text(creating ? "Create account" : "Sign in").font(.aminHeadline)
        }
        .frame(maxWidth: .infinity, minHeight: 50)
      }
      .buttonStyle(.borderedProminent).tint(.aminAccent)
      .disabled(!canSubmit)

      if !creating {
        Button("Forgot your password?") { forgot() }
          .font(.aminCaption).foregroundStyle(Color.aminAccentInk)
          .frame(maxWidth: .infinity)
          .disabled(email.isEmpty || working)
      }
      if let error {
        Label(error, systemImage: "exclamationmark.triangle").font(.aminCaption).foregroundStyle(Color.aminDanger)
      }
      if let notice {
        Label(notice, systemImage: "envelope").font(.aminCaption).foregroundStyle(Color.aminAccentInk)
      }
    }
    .padding(AminSpace.xl)
    .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.xl))
    .overlay(RoundedRectangle(cornerRadius: AminRadius.xl).strokeBorder(Color.aminLine))
  }

  private func confirm(_ address: String) -> some View {
    VStack(spacing: AminSpace.lg) {
      Image(systemName: "envelope.badge").font(.system(size: 44, weight: .light)).foregroundStyle(Color.aminAccentInk)
      Text("Check your email").font(.amin(.title2, weight: .semibold))
      Text("We sent a link to \(address). Open it on this device to finish creating your account.")
        .font(.aminBody).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
      Button("I've confirmed, sign me in") { creating = false; Task { await signInAfterConfirm() } }
        .buttonStyle(.bordered).tint(.aminAccent)
    }
    .padding(AminSpace.xl)
    .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.xl))
  }

  private var footer: some View {
    VStack(spacing: AminSpace.md) {
      Label("No analytics. No ads. Your documents are never uploaded.", systemImage: "lock.shield")
        .font(.aminCaption).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
      Button("Have an Amin computer at home? Connect to it") { connecting = true }
        .font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminAccentInk)
      HStack(spacing: AminSpace.lg) {
        Link("Privacy", destination: URL(string: "https://amin.vercel.app/privacy")!)
        Link("Terms", destination: URL(string: "https://amin.vercel.app/terms")!)
      }
      .font(.aminCaption).foregroundStyle(Color.aminMuted)
    }
  }

  private var closeButton: some ToolbarContent {
    ToolbarItem(placement: .cancellationAction) { Button("Close") { connecting = false } }
  }

  private func field(_ title: String, text: Binding<String>, prompt: String, focus f: Field) -> some View {
    VStack(alignment: .leading, spacing: AminSpace.xs) {
      Text(title).font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminMuted)
      TextField(prompt, text: text)
        .focused($focus, equals: f)
        .autocorrectionDisabled()
        #if os(iOS)
        .textInputAutocapitalization(f == .name ? .words : .never)
        #endif
        .boxedField()
    }
  }

  private var canSubmit: Bool {
    let ok = email.contains("@") && password.count >= (creating ? 8 : 1)
    return ok && !working && (!creating || !name.trimmingCharacters(in: .whitespaces).isEmpty)
  }

  private func go() {
    guard canSubmit else { return }
    working = true; error = nil; notice = nil
    let mail = email.trimmingCharacters(in: .whitespaces).lowercased()
    Task {
      defer { working = false }
      do {
        if creating {
          let lang = Locale.current.language.languageCode?.identifier ?? "en"
          try await account.signUp(email: mail, password: password, name: name.trimmingCharacters(in: .whitespaces),
                                   locale: ["ar", "ml"].contains(lang) ? lang : "en")
        } else {
          try await account.signIn(email: mail, password: password)
        }
        if account.isSignedIn { password = ""; await model.accountSignedIn() }
      } catch {
        self.error = Self.friendly(error)
      }
    }
  }

  private func signInAfterConfirm() async {
    guard !password.isEmpty, case .needsConfirmation(let mail) = account.status else { return }
    do {
      try await account.signIn(email: mail, password: password)
      if account.isSignedIn { await model.accountSignedIn() }
    } catch { self.error = Self.friendly(error) }
  }

  private func forgot() {
    Task {
      do {
        try await account.resetPassword(email: email.trimmingCharacters(in: .whitespaces).lowercased())
        notice = "If that address has an account, a reset link is on its way."
      } catch { self.error = Self.friendly(error) }
    }
  }

  /// Supabase's messages are written for developers; say it plainly.
  static func friendly(_ error: Error) -> String {
    let m = error.localizedDescription.lowercased()
    if m.contains("invalid login") || m.contains("invalid credentials") { return "That email and password don't match." }
    if m.contains("already registered") || m.contains("already exists") { return "That email already has an account. Sign in instead." }
    if m.contains("not confirmed") { return "Confirm your email first: open the link we sent you." }
    if m.contains("weak") || m.contains("password should") { return "Choose a longer password, with letters and numbers." }
    if m.contains("rate limit") { return "Too many tries. Wait a minute and try again." }
    if m.contains("offline") || m.contains("network") { return "You're offline. Connect to the internet to sign in." }
    return error.localizedDescription
  }
}
#endif
