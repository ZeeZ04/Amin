import SwiftUI

/// First run (docs/team/D1 §1, DESIGN.md): the promise, the model, the microphone, ready.
struct OnboardingView: View {
  @Environment(AppModel.self) private var model
  @Binding var done: Bool
  @State private var page = 0
  #if os(iOS) || os(macOS) || os(visionOS)
  @State private var downloader = ModelDownloader()
  @State private var offered: ModelInfo?
  #endif

  var body: some View {
    VStack(spacing: AminSpace.xl) {
      Spacer(minLength: AminSpace.xl)
      Group {
        switch page {
        case 0: promise
        case 1: modelPage
        case 2: micPage
        default: ready
        }
      }
      .frame(maxWidth: 460)
      .transition(.opacity.combined(with: .move(edge: .trailing)))
      Spacer()
      HStack(spacing: AminSpace.sm) {
        ForEach(0..<4) { i in
          Capsule().fill(i == page ? Color.aminAccent : Color.aminLine).frame(width: i == page ? 22 : 8, height: 8)
        }
      }
      .accessibilityHidden(true)
      Button(action: next) {
        Text(page == 3 ? "Start" : "Continue").font(.aminHeadline).frame(maxWidth: .infinity, minHeight: 50)
      }
      .buttonStyle(.borderedProminent).tint(.aminAccent)
      .disabled(isDownloading)
      .frame(maxWidth: 460)
      if page != 1 && page < 3 {  // never skip the model page
        Button("Skip") { done = true }.font(.aminBody).foregroundStyle(Color.aminMuted)
      }
    }
    .padding(AminSpace.xl)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Color.aminBg.ignoresSafeArea())
    .animation(AminMotion.spring, value: page)
  }

  private var isDownloading: Bool {
    #if os(iOS) || os(macOS) || os(visionOS)
    if case .downloading = downloader.state { return true }
    #endif
    return false
  }

  private func next() { if page < 3 { page += 1 } else { done = true } }

  private func header(_ symbol: String?, _ title: String, _ body: String) -> some View {
    VStack(spacing: AminSpace.lg) {
      if let symbol {
        Image(systemName: symbol).font(.system(size: 56, weight: .light)).foregroundStyle(Color.aminAccentInk)
      } else {
        DoorMark().frame(width: 96, height: 96)
      }
      Text(title).font(.amin(.largeTitle, weight: .bold)).multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)  // wrap, never truncate (DESIGN §5)
      Text(body).font(.aminBody).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var promise: some View {
    VStack(spacing: AminSpace.xl) {
      header(nil, "Amin keeps your papers at home",
             "Ask anything. When your documents hold the answer, Amin shows you the passage it came from.")
      VStack(alignment: .leading, spacing: AminSpace.md) {
        Label("Runs on your own devices. No account with us, no analytics.", systemImage: "lock.shield")
        Label("Every answer says where it came from.", systemImage: "quote.bubble")
        Label("English, العربية and മലയാളം.", systemImage: "globe")
      }
      .font(.aminBody).foregroundStyle(Color.aminInk2)
    }
  }

  @ViewBuilder private var modelPage: some View {
    #if os(iOS) || os(macOS) || os(visionOS)
    VStack(spacing: AminSpace.xl) {
      header("cpu", "Amin's own model", "Download it once from your Amin computer, and Amin can answer on this device even with no network.")
      switch downloader.state {
      case .idle:
        if let m = offered {
          VStack(spacing: AminSpace.sm) {
            Button("Download \(m.name) · \(ByteCountFormatter.string(fromByteCount: m.bytes, countStyle: .file))") {
              Task { if let c = model.client { await downloader.download(m, from: c) } }
            }
            .buttonStyle(.bordered).tint(.aminAccent)
            Text(m.purpose).font(.aminCaption).foregroundStyle(Color.aminMuted)
          }
        } else {
          Text(model.client == nil ? "Connect to your Amin computer to download the model, or choose a folder in Settings."
                                   : "Looking for the model on your Amin computer…")
            .font(.aminCaption).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
        }
      case .downloading(let f):
        ProgressView(value: f) { Text("Downloading… \(Int(f * 100))%") }.tint(.aminAccent)
        Text("Keep Amin open on your home Wi-Fi.").font(.aminCaption).foregroundStyle(Color.aminMuted)
      case .done(let dir):
        Label("Ready on this device", systemImage: "checkmark.circle.fill").foregroundStyle(Color.aminAccentInk)
          .onAppear { model.useDownloadedModel(at: dir) }
        #if targetEnvironment(simulator)
        Text("In the Simulator, answers come from your Amin computer: the model itself runs on a real iPhone, iPad or Mac.")
          .font(.aminCaption).foregroundStyle(Color.aminMuted).multilineTextAlignment(.center)
        #endif
      case .failed(let why):
        Text(why).font(.aminCaption).foregroundStyle(Color.aminDanger).multilineTextAlignment(.center)
      }
    }
    .task {
      guard offered == nil, let c = model.client, let list = try? await c.models() else { return }
      offered = ModelDownloader.recommended(from: list)
    }
    #else
    header("cpu", "Amin's own model", "This device asks your Amin computer, which runs the model.")
    #endif
  }

  private var micPage: some View {
    header("mic.fill", "Talk to Amin",
           "Say “Hey Amin” with the app open, or tap the microphone. Your voice is turned into text on this device or your Amin computer, never in the cloud.")
  }

  private var ready: some View {
    header("checkmark.seal", "You're set",
           "Add a document and ask about it, or just ask. Answers from your documents show their source.")
  }
}
