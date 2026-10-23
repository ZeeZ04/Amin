import SwiftUI

// Amin's brand, shared with the web app (amin/web/app.css): Emirati-door teal,
// keyhole saffron, sand. Everything else is system colour, so the apps follow
// light and dark mode, Increase Contrast and each platform's own materials.
extension Color {
  static let aminTeal = Color(red: 0x0E / 255, green: 0x5E / 255, blue: 0x5A / 255)
  static let aminTealDeep = Color(red: 0x0A / 255, green: 0x3F / 255, blue: 0x3C / 255)
  static let aminSaffron = Color(red: 0xE3 / 255, green: 0xA7 / 255, blue: 0x2F / 255)
  static let aminSand = Color(red: 0xF3 / 255, green: 0xEF / 255, blue: 0xE4 / 255)
}

/// The logo: a studded Emirati door with a gold keyhole, drawn as a Shape so it
/// scales from a watch complication to a Vision Pro window.
struct DoorMark: View {
  var tint: Color = .aminTeal

  var body: some View {
    Canvas { ctx, size in
      let s = min(size.width, size.height) / 512
      func p(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x * s, y: y * s) }
      var frame = Path()
      frame.move(to: p(156, 410))
      frame.addLine(to: p(156, 236))
      frame.addArc(center: p(256, 236), radius: 100 * s, startAngle: .degrees(180), endAngle: .degrees(0), clockwise: false)
      frame.addLine(to: p(356, 410))
      frame.closeSubpath()
      ctx.stroke(frame, with: .color(tint), style: StrokeStyle(lineWidth: 22 * s, lineJoin: .round))
      var seam = Path()
      seam.move(to: p(256, 140)); seam.addLine(to: p(256, 410))
      ctx.stroke(seam, with: .color(tint), lineWidth: 13 * s)
      for x in [196.0, 316.0] {
        for y in [250.0, 300.0, 350.0] {
          ctx.fill(Path(ellipseIn: CGRect(x: (x - 9) * s, y: (y - 9) * s, width: 18 * s, height: 18 * s)), with: .color(tint))
        }
      }
      ctx.fill(Path(ellipseIn: CGRect(x: 234 * s, y: 260 * s, width: 44 * s, height: 44 * s)), with: .color(.aminSaffron))
      var key = Path()
      key.move(to: p(243, 292)); key.addLine(to: p(269, 292)); key.addLine(to: p(276, 336)); key.addLine(to: p(236, 336))
      key.closeSubpath()
      ctx.fill(key, with: .color(.aminSaffron))
    }
    .aspectRatio(1, contentMode: .fit)
    .accessibilityHidden(true)
  }
}

// Apple TV has no text selection, keyboard shortcuts or bordered fields: these
// apply each one where the platform has it.
extension View {
  @ViewBuilder func selectable() -> some View {
    #if os(tvOS)
    self
    #else
    self.textSelection(.enabled)
    #endif
  }

  @ViewBuilder func boxedField() -> some View {
    #if os(tvOS) || os(watchOS)
    self
    #else
    self.textFieldStyle(.roundedBorder)
    #endif
  }

  @ViewBuilder func returnKeySends() -> some View {
    #if os(tvOS) || os(watchOS)
    self
    #else
    self.keyboardShortcut(.return, modifiers: [])
    #endif
  }
}
