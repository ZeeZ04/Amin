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
    ZStack(alignment: .top) {
      Color.aminBg
      RadialGradient(colors: [Color.aminLantern.opacity(0.10), .clear], center: .top, startRadius: 0, endRadius: 480)
    }
  }

  /// D5 sign-in hero: the door panel, the mark, and a welcome in all three languages.
  private var header: some View {
    VStack(spacing: AminSpace.xl) {
      DoorPanel {
        VStack(spacing: AminSpace.lg) {
          DoorMark(tint: .aminOnDoor).frame(width: 96, height: 96)
          WelcomeLine()
        }
        .padding(.top, 56).padding(.bottom, AminSpace.xl)
      }
      .frame(maxWidth: 300)
      VStack(spacing: AminSpace.sm) {
        Text(creating ? "Create your Amin account" : "Welcome back")
          .font(.aminSerif(.title, weight: .semibold)).foregroundStyle(Color.aminInk)
          .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        Text("Your account holds your plan, nothing else. What you ask and the documents you add stay on this device.")
          .font(.aminBody).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }
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
          .aminField()
      }

      Button(action: go) {
        HStack(spacing: AminSpace.sm) {
          if working { LanternDot(size: 10) }
          Text(creating ? "Create account" : "Sign in").font(.aminHeadline)
        }
        .frame(maxWidth: .infinity, minHeight: 52)
        .foregroundStyle(canSubmit ? Color.aminOnAccent : Color.aminMuted)
        .background(canSubmit ? Color.aminAccent : Color.aminLine.opacity(0.6), in: RoundedRectangle(cornerRadius: AminRadius.md))
      }
      .buttonStyle(.plain)
      .disabled(!canSubmit)
      if !canSubmit && !working, let hint {
        Text(hint).font(.aminCaption).foregroundStyle(Color.aminMuted).frame(maxWidth: .infinity)
      }

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
    .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.lg))
    .overlay(RoundedRectangle(cornerRadius: AminRadius.lg).strokeBorder(Color.aminLine))
    .shadow(color: Color.aminDoor.opacity(0.08), radius: 18, y: 6)
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
      Button { connecting = true } label: {
        Label("Have an Amin computer at home? Connect to it", systemImage: "desktopcomputer")
          .font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminAccentInk)
          .padding(.horizontal, AminSpace.lg).padding(.vertical, AminSpace.md)
          .frame(maxWidth: .infinity)
          .background(Color.aminAccentWash, in: RoundedRectangle(cornerRadius: AminRadius.md))
      }
      .buttonStyle(.plain)
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
        .aminField()
    }
  }

  /// Why the button is not ready yet (D5: say it, rather than show a blank grey pill).
  private var hint: String? {
    if creating && name.trimmingCharacters(in: .whitespaces).isEmpty { return "Add your name to continue." }
    if !email.contains("@") { return "Enter your email address." }
    if creating && password.count < 8 { return "Passwords need 8 or more characters." }
    if password.isEmpty { return "Enter your password." }
    return nil
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

/// "Welcome home" in Amin's three languages, changing every 4 s (still under Reduce Motion).
private struct WelcomeLine: View {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var i = 0
  private let lines: [(String, AminScript)] = [("Welcome home", .latin), ("مرحباً بك", .arabic), ("സ്വാഗതം", .malayalam)]

  var body: some View {
    Text(lines[i].0)
      .font(.aminSerif(.title2, script: lines[i].1, weight: .semibold))
      .foregroundStyle(Color.aminOnDoor)
      .contentTransition(.opacity)
      .id(i)
      .transition(.opacity)
      .task {
        guard !reduceMotion else { return }
        while !Task.isCancelled {
          try? await Task.sleep(for: .seconds(4))
          withAnimation(.easeInOut(duration: 0.6)) { i = (i + 1) % lines.count }
        }
      }
      .accessibilityLabel("Welcome home")
  }
}
#endif
