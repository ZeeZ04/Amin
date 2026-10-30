#if os(macOS) || os(iOS)
import AVFoundation
import Speech
import SwiftUI

/// Ambient mode (Task 2, docs/team/D2-voice-hud.md): a full-screen orb that
/// waits for "Hey Amin" / "Hey Ameen", then talks. Wake detection runs on
/// this device with Apple's on-device recogniser; nothing is uploaded. On
/// iPhone, Apple allows this only while the app is open; the Mac can stay on.
struct AmbientView: View {
  @Environment(AppModel.self) private var model
  @Environment(\.dismiss) private var dismiss
  @State private var wake = WakeListener()
  @State private var voice = VoiceSession()
  @State private var conversing = false

  var body: some View {
    ZStack {
      RadialGradient(colors: [AminHUD.bgCentre, AminHUD.bgEdge, AminHUD.vignette],
                     center: .center, startRadius: 40, endRadius: 1100).ignoresSafeArea()
      VStack(spacing: AminSpace.xl) {
        Spacer()
        MajlisOrb(phase: conversing ? voice.orbPhase : (wake.heardSpeech ? .listening : .idle),
                  level: conversing ? voice.level : wake.level)
          .frame(maxWidth: 440, maxHeight: 440)
          .onTapGesture { conversing ? voice.tapOrb() : begin() }
        Text(conversing ? voice.status : "Say “Hey Amin”")
          .font(.amin(.title2, weight: .semibold)).foregroundStyle(AminHUD.sand)
        if conversing {
          Text(voice.said).font(.amin(.title3)).foregroundStyle(AminHUD.textSecondary).multilineTextAlignment(.center)
          ScrollView { Text(voice.reply).font(.amin(.title3)).foregroundStyle(AminHUD.sand).multilineTextAlignment(.center) }
            .frame(maxWidth: 820, maxHeight: 260)
        }
        Spacer()
        Label("Listening happens on this device. Nothing is uploaded.", systemImage: "lock.shield")
          .font(.amin(.footnote)).foregroundStyle(AminHUD.textTertiary)
      }
      .padding(AminSpace.huge)
      // Side panels, per DESIGN.md: time and source only.
      VStack {
        HStack {
          TimelineView(.periodic(from: .now, by: 30)) { tl in
            Text(tl.date, format: .dateTime.hour().minute())
              .font(.system(size: 34, weight: .light, design: .rounded)).monospacedDigit()
              .foregroundStyle(AminHUD.sand.opacity(0.85))
          }
          Spacer()
          Button { stop(); dismiss() } label: { Image(systemName: "xmark").font(.title3) }
            .buttonStyle(.plain).foregroundStyle(AminHUD.textSecondary).accessibilityLabel("Leave ambient mode")
        }
        Spacer()
        if let source = model.turns.last?.answer, !source.isGeneral, !source.citationOrder.isEmpty {
          HStack {
            Label("From your documents · \(source.citationOrder.count) source\(source.citationOrder.count == 1 ? "" : "s")",
                  systemImage: "doc.text")
              .font(.amin(.callout)).padding(.horizontal, AminSpace.lg).padding(.vertical, AminSpace.sm)
              .background(AminHUD.panelFill, in: Capsule()).foregroundStyle(AminHUD.sand)
            Spacer()
          }
        }
      }
      .padding(AminSpace.xxl)
    }
    .task { await wake.start { begin() } }
    .onDisappear { stop() }
  }

  private func begin() {
    guard !conversing else { return }
    wake.pause()
    conversing = true
    Task {
      await voice.start(model: model)
      try? await Task.sleep(for: .milliseconds(600))  // let the session reach .listening first
      // VoiceSession ends itself after two quiet turns; then wait for the wake word again.
      while voice.state != .idle { try? await Task.sleep(for: .milliseconds(300)) }
      voice.stop()
      conversing = false
      wake.resume()
    }
  }

  private func stop() { voice.stop(); wake.stop() }
}

/// Continuous on-device recognition, watching only for the wake phrase.
@MainActor @Observable
final class WakeListener {
  private(set) var level: Double = 0
  private(set) var heardSpeech = false
  private let engine = AVAudioEngine()
  private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
  private var request: SFSpeechAudioBufferRecognitionRequest?
  private var task: SFSpeechRecognitionTask?
  private var onWake: (() -> Void)?
  private var paused = false

  nonisolated static func isWake(_ text: String) -> Bool { WakePhrase.matches(text) }

  func start(onWake: @escaping () -> Void) async {
    self.onWake = onWake
    guard await OnDeviceSpeech.authorised(), let recognizer, recognizer.supportsOnDeviceRecognition else { return }
    // The microphone first: installing a tap without permission and a recording session throws.
    #if os(iOS)
    guard await AVAudioApplication.requestRecordPermission() else { return }
    let session = AVAudioSession.sharedInstance()
    try? session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetoothHFP])
    try? session.setActive(true)
    #else
    guard await AVCaptureDevice.requestAccess(for: .audio) else { return }
    #endif
    let input = engine.inputNode
    let format = input.outputFormat(forBus: 0)
    guard format.channelCount > 0 else { return }  // no microphone (e.g. a simulator without audio input)
    input.installTap(onBus: 0, bufferSize: 1024, format: format, block: Self.tap { [weak self] buf, rms in
      guard let self else { return }
      self.level = 0.65 * self.level + 0.35 * min(1, rms * 12)
      self.request?.append(buf)
    })
    try? engine.start()
    listen()
  }

  /// The tap runs on the audio thread; it measures there and hops to the main actor.
  nonisolated private static func tap(_ onMain: @escaping @MainActor (AVAudioPCMBuffer, Double) -> Void) -> AVAudioNodeTapBlock {
    { buf, _ in
      let level = rms(buf)
      nonisolated(unsafe) let b = buf  // handed to the main actor once; the audio thread does not reuse it after the tap returns
      Task { @MainActor in onMain(b, level) }
    }
  }

  nonisolated private static func rms(_ buf: AVAudioPCMBuffer) -> Double {
    guard let ch = buf.floatChannelData?[0] else { return 0 }
    let n = Int(buf.frameLength); var s: Float = 0
    for i in 0..<n { s += ch[i] * ch[i] }
    return Double(sqrt(s / Float(max(n, 1))))
  }

  /// One recognition request; Apple caps each at about a minute, so it renews itself.
  private func listen() {
    guard !paused, let recognizer else { return }
    task?.cancel()
    let req = SFSpeechAudioBufferRecognitionRequest()
    req.requiresOnDeviceRecognition = true
    req.shouldReportPartialResults = true
    request = req
    task = recognizer.recognitionTask(with: req, resultHandler: Self.results { [weak self] text, ended in
      guard let self, !self.paused else { return }
      self.heardSpeech = !text.isEmpty
      if Self.isWake(text) {
        self.onWake?()
      } else if ended {
        self.listen()
      }
    })
  }

  /// Recognition results arrive on Speech's queue; hand only the text across.
  nonisolated private static func results(_ onMain: @escaping @MainActor (String, Bool) -> Void)
    -> @Sendable (SFSpeechRecognitionResult?, (any Error)?) -> Void {
    { result, error in
      let text = result?.bestTranscription.formattedString ?? ""
      let ended = (result?.isFinal ?? false) || error != nil
      Task { @MainActor in onMain(text, ended) }
    }
  }

  func pause() { paused = true; task?.cancel(); request = nil; engine.pause() }
  func resume() { paused = false; try? engine.start(); listen() }
  func stop() { paused = true; task?.cancel(); engine.inputNode.removeTap(onBus: 0); engine.stop() }
}
#endif
