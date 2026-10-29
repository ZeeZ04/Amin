#if os(iOS) || os(macOS) || os(visionOS)
import Foundation
import MLXLLM
import MLXLMCommon
import Tokenizers

/// Amin's own model (edge-2, Gemma 4 E4B), running on this device through MLX.
/// Nothing leaves the device: no server, no account (ADR-014).
///
/// v1 answers from the model's own knowledge, labelled "General knowledge",
/// exactly as the server's hybrid fallback does. Retrieval with citations
/// over on-device documents is the next step (the Python pipeline in amin/answer.py).
///
/// Sizes (E38): 8-bit 7.4 GB, 6-bit 5.7 GB, which Macs and M-series iPads
/// handle. iPhone apps get about 6 GB even with the increased-memory
/// entitlement, so iPhones need the 4-bit build (about 3.9 GB) or an E2B student.
/// MLX does not run in the iOS Simulator; test on a device or the Mac.
actor LocalEngine: Engine {
  let directory: URL
  private var container: ModelContainer?

  /// The same rules the server's general answers follow (amin/prompts.py GENERAL_SYSTEM).
  static let generalSystem = """
    You are Amin, a careful, helpful assistant. Your name means trustworthy.

    Answer from your own general knowledge, accurately and concisely.
    - If you are not sure, say so plainly. Never invent a figure, date or name.
    - You cannot see the user's personal documents in this answer. If the question
      is about their own details - their contract, bill, account, appliance,
      school, car or family - say you don't have that information. Do not guess.
    - Do not use source tags like [S1]; nothing here comes from a document.
    - Answer in the same language the question was asked in.
    """

  init(directory: URL) { self.directory = directory }

  /// Load once; later calls reuse the weights already in memory.
  func load() async throws -> ModelContainer {
    if let container { return container }
    guard FileManager.default.fileExists(atPath: directory.appending(path: "config.json").path()) else {
      throw AminError.server("No model found in \(directory.lastPathComponent). Choose the edge-2 folder.")
    }
    let c = try await loadModelContainer(from: directory, using: HFTokenizerLoader())
    container = c
    return c
  }

  func ask(_ question: String, project: String?, conversation: String?) async throws -> Answer {
    let started = ContinuousClock.now
    let model = try await load()
    let session = ChatSession(
      model,
      instructions: Self.generalSystem,
      generateParameters: GenerateParameters(maxTokens: 800, temperature: 0.2),
      additionalContext: ["enable_thinking": false])
    let raw = try await session.respond(to: question)
    let text = Self.clean(raw)
    let ms = Int((ContinuousClock.now - started) / .milliseconds(1))
    return Answer(question: question, outcome: "general", basis: "general",
                  claims: [Claim(text: text, citations: [], verdict: "uncited")], latencyMs: ms)
  }

  /// Drop any reasoning block and stray source tags (nothing here is cited).
  static func clean(_ s: String) -> String {
    var t = s
    if let r = t.range(of: "</think>") { t = String(t[r.upperBound...]) }
    t = t.replacingOccurrences(of: #"\s*\[S\d+\]"#, with: "", options: .regularExpression)
    return t.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
/// swift-transformers' tokenizer, adapted to MLX's `Tokenizer` protocol.
/// Written out by hand instead of MLXHuggingFace's macro, so the build needs
/// no third-party macro trusted.
struct HFTokenizerLoader: MLXLMCommon.TokenizerLoader {
  func load(from directory: URL) async throws -> any MLXLMCommon.Tokenizer {
    Bridge(try await Tokenizers.AutoTokenizer.from(modelFolder: directory))
  }

  struct Bridge: MLXLMCommon.Tokenizer {
    let upstream: any Tokenizers.Tokenizer
    init(_ upstream: any Tokenizers.Tokenizer) { self.upstream = upstream }

    func encode(text: String, addSpecialTokens: Bool) -> [Int] {
      upstream.encode(text: text, addSpecialTokens: addSpecialTokens)
    }
    func decode(tokenIds: [Int], skipSpecialTokens: Bool) -> String {
      upstream.decode(tokens: tokenIds, skipSpecialTokens: skipSpecialTokens)
    }
    func convertTokenToId(_ token: String) -> Int? { upstream.convertTokenToId(token) }
    func convertIdToToken(_ id: Int) -> String? { upstream.convertIdToToken(id) }
    var bosToken: String? { upstream.bosToken }
    var eosToken: String? { upstream.eosToken }
    var unknownToken: String? { upstream.unknownToken }

    func applyChatTemplate(messages: [[String: any Sendable]], tools: [[String: any Sendable]]?,
                           additionalContext: [String: any Sendable]?) throws -> [Int] {
      do {
        return try upstream.applyChatTemplate(messages: messages, tools: tools, additionalContext: additionalContext)
      } catch Tokenizers.TokenizerError.missingChatTemplate {
        throw MLXLMCommon.TokenizerError.missingChatTemplate
      }
    }
  }
}
#endif
