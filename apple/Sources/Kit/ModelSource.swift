#if os(iOS) || os(macOS) || os(visionOS)
import Foundation

/// Where a device gets Amin's model: the Amin computer at home (AminClient),
/// or, for people without one, Hugging Face (decision 2026-10-30), which hosts
/// openly licensed models for free. Either way it is a one-time download of
/// weights; nothing about the person is sent.
nonisolated protocol ModelSource: Sendable {
  func models() async throws -> [ModelInfo]
  func modelFile(_ model: String, _ file: String, progress: @escaping @Sendable (Int64) -> Void) async throws -> URL
}

extension AminClient: ModelSource {}

/// Amin's builds published as <org>/edge-2-m46, <org>/edge-2-q6, <org>/edge-2-q8
/// (scripts/publish_model.py).
nonisolated struct HuggingFace: ModelSource {
  let org: String
  var session: URLSession = .shared

  static let builds = [
    ("edge-2-m46", "Made for iPhone"),
    ("edge-2-q6", "Made for iPad and Mac"),
    ("edge-2-q8", "The fullest model, for Macs"),
  ]

  /// The org from Config/Secrets.xcconfig, or nil when the build has none.
  static var configured: HuggingFace? {
    guard let org = Bundle.main.object(forInfoDictionaryKey: "AminHFModelOrg") as? String, !org.isEmpty else { return nil }
    return HuggingFace(org: org)
  }

  private struct Repo: Decodable {
    struct Sibling: Decodable { let rfilename: String; let size: Int64? }
    let siblings: [Sibling]
  }

  /// Model files only: weights, config and tokenizer, not the README or .gitattributes.
  static func wanted(_ file: String) -> Bool {
    file.hasSuffix(".safetensors") || file.hasSuffix(".json") || file.hasSuffix(".jinja") || file == "tokenizer.model"
  }

  func models() async throws -> [ModelInfo] {
    var out: [ModelInfo] = []
    for (name, purpose) in Self.builds {
      let url = URL(string: "https://huggingface.co/api/models/\(org)/\(name)?blobs=true")!
      guard let (data, res) = try? await session.data(from: url),
            (res as? HTTPURLResponse)?.statusCode == 200,
            let repo = try? JSONDecoder().decode(Repo.self, from: data) else { continue }
      let files = repo.siblings.filter { Self.wanted($0.rfilename) }
        .map { ModelInfo.File(name: $0.rfilename, bytes: $0.size ?? 0) }
      guard files.contains(where: { $0.name == "config.json" }) else { continue }
      out.append(ModelInfo(name: name, purpose: purpose, bytes: files.reduce(0) { $0 + $1.bytes }, files: files))
    }
    if out.isEmpty { throw AminError.server("Couldn't reach the model download. Check your internet connection.") }
    return out
  }

  func modelFile(_ model: String, _ file: String, progress: @escaping @Sendable (Int64) -> Void) async throws -> URL {
    let url = URL(string: "https://huggingface.co/\(org)/\(model)/resolve/main/\(file)")!
    let (tmp, res) = try await session.download(from: url, delegate: DownloadProgress(progress))
    guard (res as? HTTPURLResponse)?.statusCode == 200 else {
      throw AminError.server("Couldn't download \(file). Check your internet connection and try again.")
    }
    return tmp
  }
}
#endif
