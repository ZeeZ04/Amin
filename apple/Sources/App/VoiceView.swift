#if os(iOS) || os(macOS) || os(visionOS)
import AVFoundation
import SwiftUI

/// Voice mode: listen → (pause) → transcribe on the Amin computer → ask →
/// speak → listen again. The same loop as the web app (E37).
struct VoiceView: View {
  @Environment(AppModel.self) private var model
  @Environment(\.dismiss) private var dismiss
  @State private var voice = VoiceSession()

  var body: some View {
    VStack(spacing: 22) {
      Spacer()
      Button(action: voice.tapOrb) {
        Circle()
          .fill(RadialGradient(colors: voice.state == .speaking
                               ? [Color(red: 0.91, green: 0.96, blue: 0.95), Color(red: 0.16, green: 0.55, blue: 0.52)]
                               : [Color(red: 1, green: 0.9, blue: 0.68), .aminSaffron, Color(red: 0.6, green: 0.42, blue: 0.07)],
                               center: UnitPoint(x: 0.4, y: 0.35), startRadius: 4, endRadius: 110))
          .frame(width: 170, height: 170)
          .scaleEffect(0.82 + voice.level * 0.3)
          .shadow(color: .aminSaffron.opacity(0.35 + voice.level * 0.45), radius: 30 + voice.level * 60)
          .saturation(voice.state == .idle ? 0.4 : 1)
          .animation(.linear(duration: 0.08), value: voice.level)
          .phaseAnimator([1.0, 0.92], trigger: voice.state) { c, s in
            c.scaleEffect(voice.state == .thinking || voice.state == .transcribing ? s : 1)
          }
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Tap to talk or interrupt")

      Text(voice.status).font(.title3.weight(.semibold))
      Text(voice.said).font(.body).multilineTextAlignment(.center).opacity(0.9)
      ScrollView { Text(voice.reply).font(.callout).multilineTextAlignment(.center).opacity(0.75) }
        .frame(maxHeight: 180)
      Spacer()
      Button { voice.stop(); dismiss() } label: {
        Label("End conversation", systemImage: "xmark").padding(.horizontal, 8)
      }
      .buttonStyle(.bordered).tint(.aminSand)
      Label("Your voice is transcribed on your Amin computer, not in the cloud.", systemImage: "lock")
        .font(.caption).opacity(0.7)
    }
    .foregroundStyle(Color.aminSand)
    .padding(28)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(RadialGradient(colors: [Color(red: 0.06, green: 0.35, blue: 0.34), .aminTealDeep, Color(red: 0.02, green: 0.18, blue: 0.17)],
                               center: UnitPoint(x: 0.5, y: 0.35), startRadius: 20, endRadius: 700).ignoresSafeArea())
    .task { await voice.start(model: model) }
    .onDisappear { voice.stop() }
  }
}

@MainActor @Observable
final class VoiceSession: NSObject, @preconcurrency AVSpeechSynthesizerDelegate {
  enum State { case idle, listening, transcribing, thinking, speaking }

  private(set) var state: State = .idle
  private(set) var status = "Starting…"
  private(set) var level: Double = 0
  private(set) var said = ""
  private(set) var reply = ""

  private var model: AppModel?
  private var recorder: AVAudioRecorder?
  private let synth = AVSpeechSynthesizer()
  private var loop: Task<Void, Never>?
  private var quietTurns = 0
  private var speechDone: CheckedContinuation<Void, Never>?

  private let speechDB: Float = -38, endSilence = 1.3, noSpeech = 7.0, maxTurn = 30.0

  func start(model: AppModel) async {
    self.model = model
    synth.delegate = self
    guard await Self.permission() else { status = "Amin needs microphone access. Allow it in Settings."; return }
    #if os(iOS) || os(visionOS)
    try? AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .spokenAudio, options: [.defaultToSpeaker, .allowBluetoothHFP])
    try? AVAudioSession.sharedInstance().setActive(true)
    #endif
    run()
  }

  func stop() {
    loop?.cancel(); loop = nil
    recorder?.stop(); recorder = nil
    synth.stopSpeaking(at: .immediate)
    speechDone?.resume(); speechDone = nil
    state = .idle
  }

  func tapOrb() {
    switch state {
    case .speaking: synth.stopSpeaking(at: .immediate)      // interrupt; the loop listens next
    case .listening: recorder?.stop()                       // done talking
    case .idle: quietTurns = 0; run()
    default: break
    }
  }

  private func run() {
    loop?.cancel()
    loop = Task { [weak self] in
      while let self, !Task.isCancelled {
        guard let audio = await self.listen() else {
          self.quietTurns += 1
          if self.quietTurns >= 2 { self.state = .idle; self.status = "Tap the orb to talk"; return }
          continue
        }
        self.quietTurns = 0
        await self.handle(audio)
      }
    }
  }

  /// One turn of listening: nil if nobody spoke.
  private func listen() async -> Data? {
    state = .listening; status = "Listening…"
    let url = FileManager.default.temporaryDirectory.appending(path: "amin-turn.m4a")
    let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 16_000, AVNumberOfChannelsKey: 1,
                                   AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue]
    guard let rec = try? AVAudioRecorder(url: url, settings: settings) else { status = "The microphone isn't available."; return nil }
    rec.isMeteringEnabled = true
    recorder = rec
    rec.record()
    let started = Date.now
    var spoke = false, lastVoice = Date.now
    while rec.isRecording, !Task.isCancelled {
      try? await Task.sleep(for: .milliseconds(60))
      rec.updateMeters()
      let db = rec.averagePower(forChannel: 0)
      level = Double(max(0, min(1, (db + 50) / 40)))
      if db > speechDB { spoke = true; lastVoice = .now }
      let now = Date.now
      if (spoke && now.timeIntervalSince(lastVoice) > endSilence) || (!spoke && now.timeIntervalSince(started) > noSpeech)
          || now.timeIntervalSince(started) > maxTurn { rec.stop() }
    }
    level = 0
    recorder = nil
    return spoke ? try? Data(contentsOf: url) : nil
  }

  private func handle(_ audio: Data) async {
    guard let model, let client = model.client else { return }
    state = .transcribing; status = "Transcribing…"
    guard let heard = try? await client.transcribe(audio, contentType: "audio/mp4", lang: nil), !heard.text.isEmpty else { return }
    said = heard.text; reply = ""
    state = .thinking; status = "Thinking…"
    guard let answer = await model.ask(heard.text) else { return }
    reply = answer.text
    await speak(answer.text)
  }

  private func speak(_ text: String) async {
    let lang = text.unicodeScalars.contains { (0x0D00...0x0D7F).contains($0.value) } ? "ml"
      : text.unicodeScalars.contains { (0x0600...0x06FF).contains($0.value) } ? "ar" : "en"
    guard let voice = AVSpeechSynthesisVoice.speechVoices().first(where: { $0.language.hasPrefix(lang) }) else {
      state = .speaking
      status = lang == "ml" ? "No Malayalam voice on this device yet. The answer is on screen." : "No voice for this language here."
      try? await Task.sleep(for: .seconds(2.5))
      return
    }
    let u = AVSpeechUtterance(string: text)
    u.voice = voice
    state = .speaking; status = "Speaking…"
    await withCheckedContinuation { cont in
      speechDone = cont
      synth.speak(u)
    }
  }

  nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { Task { @MainActor in self.finishSpeech() } }
  nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { Task { @MainActor in self.finishSpeech() } }
  private func finishSpeech() { speechDone?.resume(); speechDone = nil }

  private static func permission() async -> Bool {
    #if os(macOS)
    return await AVCaptureDevice.requestAccess(for: .audio)
    #else
    return await AVAudioApplication.requestRecordPermission()
    #endif
  }
}
#endif
