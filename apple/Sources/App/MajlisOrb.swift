import SwiftUI

/// The voice HUD's orb (docs/team/D2-voice-hud.md, DESIGN.md): a saffron
/// lantern core inside teal rings, with a 60-tick astrolabe dial. One Canvas
/// inside one TimelineView, drawn with transform and opacity only.
struct MajlisOrb: View {
  enum Phase: Equatable { case idle, listening, thinking, speaking, interrupted }

  var phase: Phase
  /// Smoothed microphone level, 0…1 (DESIGN §4: alpha 0.35 over (dB+50)/40).
  var level: Double
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    TimelineView(.animation(minimumInterval: phase == .idle ? 1 / 30 : 1 / 60, paused: reduceMotion)) { tl in
      Canvas { ctx, size in
        let t = tl.date.timeIntervalSinceReferenceDate
        draw(&ctx, size: size, t: reduceMotion ? 0 : t)
      }
    }
    .aspectRatio(1, contentMode: .fit)
    .accessibilityElement()
    .accessibilityLabel(label)
    .animation(AminMotion.adaptive(reduceMotion, AminMotion.bouncy), value: phase)
  }

  private var label: String {
    switch phase {
    case .idle: "Amin, waiting"
    case .listening: "Amin, listening"
    case .thinking: "Amin, thinking"
    case .speaking: "Amin, speaking"
    case .interrupted: "Amin, stopped"
    }
  }

  private func draw(_ ctx: inout GraphicsContext, size: CGSize, t: Double) {
    let c = CGPoint(x: size.width / 2, y: size.height / 2)
    let r = min(size.width, size.height) / 2
    let active = phase != .idle
    let breathe = 0.5 + 0.5 * sin(t * 2 * .pi / AminMotion.breathe)
    let lvl = phase == .listening ? level : 0
    // Speaking pulses at speech rhythm; thinking holds a slow orbit.
    let pulse = phase == .speaking ? 0.5 + 0.5 * sin(t * 2 * .pi * 2.2) : 0

    // 1. Outer glow, which grows with the voice.
    let glowR = r * (0.62 + 0.10 * lvl + 0.04 * breathe)
    let glowColor = phase == .speaking ? AminHUD.coreSpeaking : AminHUD.glow
    ctx.fill(Path(ellipseIn: CGRect(x: c.x - glowR * 1.5, y: c.y - glowR * 1.5, width: glowR * 3, height: glowR * 3)),
             with: .radialGradient(Gradient(colors: [glowColor.opacity(active ? 0.28 + 0.3 * lvl : 0.12), .clear]),
                                   center: c, startRadius: 0, endRadius: glowR * 1.5))

    // 2. The 60-tick astrolabe dial. Ticks brighten around the current level;
    //    thinking sweeps a bright arc around the dial.
    let tickBase = active ? 0.45 : 0.18
    for i in 0..<60 {
      let a = Double(i) / 60 * 2 * .pi - .pi / 2
      let major = i % 5 == 0
      let inner = r * (major ? 0.86 : 0.89), outer = r * 0.95
      var sweep = 0.0
      if phase == .thinking {
        let head = (t * 0.6).truncatingRemainder(dividingBy: 1) * 2 * .pi
        let d = abs(atan2(sin(a + .pi / 2 - head), cos(a + .pi / 2 - head)))
        sweep = max(0, 1 - d / 0.9)
      }
      let wave = phase == .listening ? lvl * (0.5 + 0.5 * sin(Double(i) * 0.7 + t * 6)) : 0
      var p = Path()
      p.move(to: CGPoint(x: c.x + cos(a) * inner, y: c.y + sin(a) * inner))
      p.addLine(to: CGPoint(x: c.x + cos(a) * (outer + r * 0.05 * wave), y: c.y + sin(a) * (outer + r * 0.05 * wave)))
      let o = min(1, tickBase + 0.5 * sweep + 0.4 * wave)
      ctx.stroke(p, with: .color((sweep > 0.05 ? AminHUD.glow : AminHUD.sand).opacity(o)),
                 lineWidth: major ? 2.2 : 1.2)
    }

    // 3. Two teal rings, counter-rotating slowly when active.
    for (k, rr) in [0.74, 0.80].enumerated() {
      let ring = Path(ellipseIn: CGRect(x: c.x - r * rr, y: c.y - r * rr, width: r * rr * 2, height: r * rr * 2))
      let spin = active ? t * (k == 0 ? 0.25 : -0.18) : 0
      var g = ctx
      g.translateBy(x: c.x, y: c.y); g.rotate(by: .radians(spin)); g.translateBy(x: -c.x, y: -c.y)
      g.stroke(ring, with: .color(AminHUD.sand.opacity(active ? 0.55 : 0.2)),
               style: StrokeStyle(lineWidth: 1.4, dash: k == 0 ? [r * 0.18, r * 0.06] : [r * 0.02, r * 0.05]))
    }

    // 4. The lantern core: saffron while listening, teal while speaking.
    let coreR = r * (0.46 + 0.10 * lvl + 0.03 * breathe + 0.05 * pulse) * (phase == .interrupted ? 0.9 : 1)
    let colors: [Color] = phase == .speaking
      ? [Color(red: 0.91, green: 0.96, blue: 0.95), AminHUD.coreSpeaking, AminHUD.coreSpeakingDeep]
      : [AminHUD.glow, AminHUD.coreListening, Color(red: 0.6, green: 0.42, blue: 0.07)]
    let core = Path(ellipseIn: CGRect(x: c.x - coreR, y: c.y - coreR, width: coreR * 2, height: coreR * 2))
    // Idle: the lantern dims (brightness), not fades (opacity): fading it over teal turns it olive.
    let lit = active ? colors : colors.map { $0.mix(with: AminHUD.bgCentre, by: 0.35) }
    ctx.fill(core, with: .radialGradient(Gradient(colors: lit),
                                         center: CGPoint(x: c.x - coreR * 0.2, y: c.y - coreR * 0.3),
                                         startRadius: 2, endRadius: coreR * 1.2))
    // 5. The door, drawn faintly inside the lantern: the brand at the heart of the HUD.
    let d = coreR * 0.42
    var door = Path()
    door.move(to: CGPoint(x: c.x - d * 0.6, y: c.y + d))
    door.addLine(to: CGPoint(x: c.x - d * 0.6, y: c.y - d * 0.1))
    door.addArc(center: CGPoint(x: c.x, y: c.y - d * 0.1), radius: d * 0.6, startAngle: .degrees(180), endAngle: .degrees(0), clockwise: false)
    door.addLine(to: CGPoint(x: c.x + d * 0.6, y: c.y + d))
    ctx.stroke(door, with: .color(AminHUD.bgCentre.opacity(0.35)), lineWidth: max(1.5, d * 0.08))
  }
}
