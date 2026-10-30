#if os(iOS) || os(macOS) || os(visionOS)
import Auth
import Foundation
import Observation
import RevenueCat

/// The person's Amin account (decision 2026-10-30): Supabase holds the account
/// and the plan, nothing else. Questions, documents and memory never reach it.
/// RevenueCat sells Pro and tells Supabase through its webhook
/// (backend/supabase/functions/revenuecat-webhook), keyed by the Supabase user id.
///
/// With no keys in Config/Secrets.xcconfig, `isConfigured` is false and the
/// app works as before: an Amin computer, or a model on this device.
@Observable
final class Account {
  enum Status: Equatable { case unknown, signedOut, signedIn(email: String), needsConfirmation(email: String) }

  private(set) var status: Status = .unknown
  private(set) var isPro = false
  private(set) var displayName: String?

  /// Free plan: this many documents on the device; Pro has no limit.
  static let freeDocumentLimit = 5
  static let proEntitlement = "pro"
  static let callback = URL(string: "amin://auth-callback")!

  private let auth: AuthClient?
  private let base: URL?
  private let anonKey: String
  private let revenueCatKey: String

  init(bundle: Bundle = .main) {
    let url = (bundle.object(forInfoDictionaryKey: "AminSupabaseURL") as? String).flatMap(URL.init(string:))
    anonKey = bundle.object(forInfoDictionaryKey: "AminSupabaseAnonKey") as? String ?? ""
    revenueCatKey = bundle.object(forInfoDictionaryKey: "AminRevenueCatKey") as? String ?? ""
    if let url, url.host() != nil, !anonKey.isEmpty {
      base = url
      auth = AuthClient(configuration: .init(
        url: url.appending(path: "auth/v1"),
        headers: ["apikey": anonKey],
        flowType: .pkce,
        localStorage: KeychainLocalStorage()))
    } else {
      base = nil
      auth = nil
      status = .signedOut
    }
  }

  var isConfigured: Bool { auth != nil }
  var isSignedIn: Bool { if case .signedIn = status { true } else { false } }
  var sellsPro: Bool { isConfigured && !revenueCatKey.isEmpty }

  /// Restore the saved session at launch.
  func restore() async {
    guard let auth else { return }
    if let session = try? await auth.session {
      await signedIn(session.user)
    } else {
      status = .signedOut
    }
  }

  func signUp(email: String, password: String, name: String, locale: String) async throws {
    guard let auth else { throw AminError.server("Accounts aren't set up in this build.") }
    let r = try await auth.signUp(email: email, password: password,
                                  data: ["display_name": .string(name), "locale": .string(locale)],
                                  redirectTo: Self.callback)
    if let session = r.session {
      await signedIn(session.user)
    } else {
      status = .needsConfirmation(email: email)  // Supabase sent a confirmation email
    }
  }

  func signIn(email: String, password: String) async throws {
    guard let auth else { throw AminError.server("Accounts aren't set up in this build.") }
    let session = try await auth.signIn(email: email, password: password)
    await signedIn(session.user)
  }

  func resetPassword(email: String) async throws {
    try await auth?.resetPasswordForEmail(email, redirectTo: Self.callback)
  }

  /// The confirmation or password-reset link opens the app at amin://auth-callback.
  func handle(_ url: URL) async {
    guard let auth, url.scheme == "amin" else { return }
    if let session = try? await auth.session(from: url) { await signedIn(session.user) }
  }

  func signOut() async {
    try? await auth?.signOut()
    if Purchases.isConfigured { _ = try? await Purchases.shared.logOut() }
    status = .signedOut
    isPro = false
    displayName = nil
  }

  /// Delete the account from Supabase (App Store 5.1.1(v)). Data on the device
  /// stays until the app is deleted; a store subscription is cancelled by the
  /// person in their Apple ID settings.
  func deleteAccount() async throws {
    guard let auth, let base else { return }
    let token = try await auth.session.accessToken
    var req = URLRequest(url: base.appending(path: "functions/v1/delete-account"))
    req.httpMethod = "POST"
    req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    req.setValue(anonKey, forHTTPHeaderField: "apikey")
    let (_, res) = try await URLSession.shared.data(for: req)
    guard (res as? HTTPURLResponse)?.statusCode == 200 else {
      throw AminError.server("Your account could not be deleted. Try again, or email support.")
    }
    try? await auth.signOut()
    status = .signedOut
    isPro = false
  }

  /// Pro, from RevenueCat right after a purchase, else from the account's plan in Supabase.
  func refreshPlan() async {
    if Purchases.isConfigured, let info = try? await Purchases.shared.customerInfo(),
       info.entitlements[Self.proEntitlement]?.isActive == true {
      isPro = true
      return
    }
    isPro = (try? await serverSaysPro()) ?? false
  }

  private func serverSaysPro() async throws -> Bool {
    guard let auth, let base else { return false }
    let token = try await auth.session.accessToken
    var req = URLRequest(url: base.appending(path: "rest/v1/rpc/is_pro"))
    req.httpMethod = "POST"
    req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    req.setValue(anonKey, forHTTPHeaderField: "apikey")
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = Data("{}".utf8)
    let (data, _) = try await URLSession.shared.data(for: req)
    return (try? JSONDecoder().decode(Bool.self, from: data)) ?? false
  }

  private func signedIn(_ user: User) async {
    status = .signedIn(email: user.email ?? "")
    if case .string(let name)? = user.userMetadata["display_name"] { displayName = name }
    if !revenueCatKey.isEmpty {
      if Purchases.isConfigured {
        _ = try? await Purchases.shared.logIn(user.id.uuidString.lowercased())
      } else {
        Purchases.configure(withAPIKey: revenueCatKey, appUserID: user.id.uuidString.lowercased())
      }
    }
    await refreshPlan()
  }
}
#endif
