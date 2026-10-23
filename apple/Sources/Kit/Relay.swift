#if canImport(WatchConnectivity) && (os(iOS) || os(watchOS))
import Foundation
import WatchConnectivity

/// The Watch asks through the paired iPhone, which is already signed in.
/// Message: ["ask": question] → reply: ["text": …, "basis": …] or ["error": …].
nonisolated enum RelayKey {
  static let ask = "ask", text = "text", basis = "basis", error = "error"
}

#if os(iOS)
/// iPhone side: answers the Watch with whatever engine the app is using.
final class RelayServer: NSObject, WCSessionDelegate {
  private let engine: @Sendable () -> (any Engine)?

  init(engine: @escaping @Sendable () -> (any Engine)?) {
    self.engine = engine
    super.init()
    guard WCSession.isSupported() else { return }
    WCSession.default.delegate = self
    WCSession.default.activate()
  }

  nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                           replyHandler: @escaping ([String: Any]) -> Void) {
    guard let question = message[RelayKey.ask] as? String else { return replyHandler([RelayKey.error: "Nothing was asked."]) }
    let reply = UncheckedReply(replyHandler)
    let engine = engine
    Task {
      guard let engine = await MainActor.run(body: { engine() }) else {
        return reply.send([RelayKey.error: "Open Amin on your iPhone and sign in first."])
      }
      do {
        let answer = try await engine.ask(question, project: nil, conversation: nil)
        reply.send([RelayKey.text: answer.text, RelayKey.basis: answer.basis])
      } catch {
        reply.send([RelayKey.error: error.localizedDescription])
      }
    }
  }

  nonisolated func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {}
  nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}
  nonisolated func sessionDidDeactivate(_ session: WCSession) { WCSession.default.activate() }
}

/// WatchConnectivity's reply handler is not Sendable, but it is called exactly
/// once, from one place, after the work finishes.
private nonisolated struct UncheckedReply: @unchecked Sendable {
  let handler: ([String: Any]) -> Void
  init(_ h: @escaping ([String: Any]) -> Void) { handler = h }
  func send(_ m: [String: Any]) { handler(m) }
}
#endif

#if os(watchOS)
/// Watch side.
final class RelayClient: NSObject, WCSessionDelegate {
  override init() {
    super.init()
    WCSession.default.delegate = self
    WCSession.default.activate()
  }

  func ask(_ question: String) async throws -> (text: String, general: Bool) {
    guard WCSession.default.isReachable else {
      throw AminError.server("Your iPhone isn't reachable. Keep it nearby with Amin installed.")
    }
    return try await withCheckedThrowingContinuation { cont in
      WCSession.default.sendMessage([RelayKey.ask: question], replyHandler: { reply in
        if let error = reply[RelayKey.error] as? String {
          cont.resume(throwing: AminError.server(error))
        } else {
          cont.resume(returning: (reply[RelayKey.text] as? String ?? "", reply[RelayKey.basis] as? String == "general"))
        }
      }, errorHandler: { error in
        cont.resume(throwing: AminError.server(error.localizedDescription))
      })
    }
  }

  nonisolated func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {}
}
#endif
#endif
