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
        MajlisOrb(phase: voice.orbPhase, level: voice.level)
          .frame(width: 260, height: 260)
      }
      .buttonStyle(.plain)
      .accessibilityHint("Tap to talk, or to interrupt Amin")

      Text(voice.status).font(.amin(.title3, weight: .semibold)).foregroundStyle(AminHUD.sand)
      Text(voice.said).font(.amin(.title3)).multilineTextAlignment(.center).foregroundStyle(AminHUD.textSecondary)
      ScrollView { Text(voice.reply).font(.amin(.body)).multilineTextAlignment(.center).foregroundStyle(AminHUD.sand) }
        .frame(maxHeight: 200)
      Spacer()
      Button { voice.stop(); dismiss() } label: {
        Label("End conversation", systemImage: "xmark").padding(.horizontal, 8)
      }
      .buttonStyle(.bordered).tint(.aminSand)
      Label(model.client == nil ? "Your voice is transcribed on this device, not in the cloud."
                                : "Your voice is transcribed on your Amin computer, not in the cloud.", systemImage: "lock")
        .font(.caption).opacity(0.7)
    }
    .foregroundStyle(Color.aminSand)
    .padding(28)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(RadialGradient(colors: [AminHUD.bgCentre, AminHUD.bgEdge, AminHUD.vignette],
                               center: UnitPoint(x: 0.5, y: 0.38), startRadius: 20, endRadius: 760).ignoresSafeArea())
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
  private var interruptedAt: Date?

  var orbPhase: MajlisOrb.Phase {
    if let t = interruptedAt, Date.now.timeIntervalSince(t) < AminMotion.interrupt * 4 { return .interrupted }
    switch state {
    case .idle: return .idle
    case .listening: return .listening
    case .transcribing, .thinking: return .thinking
    case .speaking: return .speaking
    }
  }

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
    case .speaking: interruptedAt = .now; synth.stopSpeaking(at: .immediate)  // interrupt; the loop listens next
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
      level = 0.65 * level + 0.35 * Double(max(0, min(1, (db + 50) / 40)))
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
    guard let model else { return }
    state = .transcribing; status = "Transcribing…"
    let text: String?
    if let client = model.client {
      text = try? await client.transcribe(audio, contentType: "audio/mp4", lang: nil).text
    } else {
      text = await OnDeviceSpeech.transcribe(FileManager.default.temporaryDirectory.appending(path: "amin-turn.m4a"))
    }
    guard let heard = text?.trimmingCharacters(in: .whitespaces), !heard.isEmpty else { return }
    said = heard; reply = ""
    state = .thinking; status = "Thinking…"
    guard let answer = await model.ask(heard) else { return }
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
