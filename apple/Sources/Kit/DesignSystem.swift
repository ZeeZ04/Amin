import SwiftUI
#if canImport(UIKit) && !os(watchOS)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// Amin design system tokens (resolved values: docs/team/DESIGN.md). Source of truth: docs/team/D4-design-system.md.
// Mirrors amin/web/app.css :root. Brand colours (aminTeal, aminSaffron...) stay in Theme.swift.

// nonisolated: UIKit and AppKit resolve dynamic colours off the main thread while
// rendering; under the main-actor default the provider closure would trap.
nonisolated private func hex(_ v: UInt32) -> Color {
  Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
}

/// Light, dark, and Increase Contrast variants of each role. watchOS is always dark.
nonisolated private func role(_ l: UInt32, _ d: UInt32, lHC: UInt32, dHC: UInt32) -> Color {
  #if canImport(UIKit) && !os(watchOS)
  func ui(_ v: UInt32) -> UIColor {
    UIColor(red: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255, blue: CGFloat(v & 0xFF) / 255, alpha: 1)
  }
  return Color(UIColor { t in
    let dark = t.userInterfaceStyle == .dark, hc = t.accessibilityContrast == .high
    return ui(dark ? (hc ? dHC : d) : (hc ? lHC : l))
  })
  #elseif canImport(AppKit)
  func ns(_ v: UInt32) -> NSColor {
    NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255, blue: CGFloat(v & 0xFF) / 255, alpha: 1)
  }
  return Color(NSColor(name: nil) { a in
    let dark = a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
    let hc = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
    return ns(dark ? (hc ? dHC : d) : (hc ? lHC : l))
  })
  #else
  return hex(dHC)
  #endif
}

extension Color {
  // Surfaces
  static let aminBg = role(0xF7F8F6, 0x0D1615, lHC: 0xFFFFFF, dHC: 0x000000)
  static let aminSurface = role(0xFFFFFF, 0x131E1D, lHC: 0xFFFFFF, dHC: 0x0D1615)
  static let aminRaised = role(0xFFFFFF, 0x182524, lHC: 0xFFFFFF, dHC: 0x182524)
  static let aminSidebar = role(0xEFF2F0, 0x0F1A19, lHC: 0xEFF2F0, dHC: 0x0D1615)
  // Text
  static let aminInk = role(0x142826, 0xE5EDEB, lHC: 0x0A1514, dHC: 0xFFFFFF)
  static let aminInk2 = role(0x3C504D, 0xC3D0CD, lHC: 0x142826, dHC: 0xFFFFFF)
  static let aminMuted = role(0x5F706D, 0x8FA19E, lHC: 0x3C504D, dHC: 0xC3D0CD)
  // Brand roles
  static let aminAccent = role(0x0E5E5A, 0x1F7A72, lHC: 0x0A3F3C, dHC: 0x9BE0D6)      // fills, with aminOnAccent text
  static let aminOnAccent = role(0xFFFFFF, 0xFFFFFF, lHC: 0xFFFFFF, dHC: 0x0D1615)
  static let aminAccentInk = role(0x0E5E5A, 0x6CC5BA, lHC: 0x0A3F3C, dHC: 0x9BE0D6)   // teal as text or icon
  static let aminAccentWash = role(0xE3EFEC, 0x173533, lHC: 0xD2E6E2, dHC: 0x1F4744)
  static let aminFocus = role(0x0E5E5A, 0xE3A72F, lHC: 0x0A3F3C, dHC: 0xFFD166)       // saffron fails 3:1 on light
  static let aminGold = role(0xE3A72F, 0xE3A72F, lHC: 0xE3A72F, dHC: 0xFFD166)        // decorative only, never text on light
  static let aminOnGold = hex(0x3A2A05)
  // Lines and status
  static let aminLine = role(0xE0E6E3, 0x22312F, lHC: 0x5F706D, dHC: 0x8FA19E)
  static let aminLineStrong = role(0x8A9895, 0x5E726F, lHC: 0x3C504D, dHC: 0xC3D0CD) // control borders, 3:1
  static let aminDanger = role(0xA2322B, 0xEC8A80, lHC: 0x7E1F1A, dHC: 0xFFB3AB)
  static let aminDangerWash = role(0xFBEAE8, 0x3A1E1B, lHC: 0xF6D5D1, dHC: 0x4A1F1B)
}

/// Writing system of a string. Drives font face and line height.
enum AminScript { case latin, arabic, malayalam }

extension Font {
  /// Text style with the right face. Latin and Arabic use the system font (SF Pro / SF Arabic pick themselves
  /// per glyph); Malayalam uses the bundled Noto Sans Malayalam, scaled with Dynamic Type via relativeTo.
  static func amin(_ style: TextStyle, script: AminScript = .latin, weight: Weight = .regular) -> Font {
    switch script {
    case .latin, .arabic: return .system(style).weight(weight)
    case .malayalam: return .custom("Noto Sans Malayalam", size: aminSize(style), relativeTo: style).weight(weight)
    }
  }
  /// Default point size per style at the Large Dynamic Type setting.
  static func aminSize(_ s: TextStyle) -> CGFloat {
    switch s {
    case .largeTitle: 34
    case .title: 28
    case .title2: 22
    case .title3: 20
    case .headline, .body: 17
    case .callout: 16
    case .subheadline: 15
    case .footnote: 13
    case .caption: 12
    case .caption2: 11
    default: 17
    }
  }
  static let aminTitle = Font.amin(.title2, weight: .semibold)
  static let aminHeadline = Font.amin(.headline, weight: .semibold)
  static let aminBody = Font.amin(.body)
  static let aminAnswer = Font.amin(.body)                 // answer card text, measure 46rem
  static let aminCaption = Font.amin(.caption)             // citation chip
  static let aminMono = Font.system(.callout, design: .monospaced)
}

extension AminScript {
  /// Extra line spacing as a fraction of the point size, on top of the system default.
  var extraLeading: CGFloat {
    switch self {
    case .latin: 0
    case .arabic: 0.12
    case .malayalam: 0.22
    }
  }
}

extension View {
  func aminLineHeight(_ script: AminScript, style: Font.TextStyle = .body) -> some View {
    lineSpacing(Font.aminSize(style) * script.extraLeading)
  }
}

/// Spacing on a 4 pt grid. Use leading/trailing, never left/right, so Arabic mirrors.
enum AminSpace {
  static let xxs: CGFloat = 2
  static let xs: CGFloat = 4
  static let sm: CGFloat = 8
  static let md: CGFloat = 12
  static let lg: CGFloat = 16
  static let xl: CGFloat = 24
  static let xxl: CGFloat = 32
  static let huge: CGFloat = 48
  static let minTarget: CGFloat = 44   // 60 on visionOS, 66 on tvOS
}

enum AminRadius {
  static let sm: CGFloat = 8     // chips, fields' inner elements
  static let md: CGFloat = 12    // buttons, fields
  static let lg: CGFloat = 16    // cards
  static let xl: CGFloat = 22    // sheets, composer
  static let pill: CGFloat = 999 // voice HUD citation chips only
}

enum AminMotion {
  static let quick = 0.15        // press, hover
  static let standard = 0.25     // state change
  static let slow = 0.40         // panel, sheet
  static let breathe = 4.0       // orb idle breathing period, seconds
  static let interrupt = 0.15    // HUD interrupt snap (D2 said 120-160 ms)
  static let spring = Animation.spring(response: 0.35, dampingFraction: 0.85)
  static let bouncy = Animation.spring(response: 0.45, dampingFraction: 0.7)  // orb only
  static func adaptive(_ reduceMotion: Bool, _ a: Animation = spring) -> Animation? {
    reduceMotion ? .easeInOut(duration: quick) : a
  }
}

/// Voice HUD ("Majlis Orb") palette. The HUD is always dark, so these are fixed, not adaptive.
/// Resolved against D2: panels use AminRadius.lg (16), state transitions use AminMotion.standard (250 ms).
enum AminHUD {
  static let bgCentre = hex(0x0A3F3C)
  static let bgEdge = hex(0x062E2C)
  static let vignette = hex(0x031A19)
  static let sand = hex(0xF3EFE4)              // answer text, ring/tick base (use opacity 0.18 idle, 0.70 active)
  static let textSecondary = hex(0xBFD6D2)
  static let textTertiary = hex(0x9FC1BB)
  static let coreListening = hex(0xE3A72F)
  static let glow = hex(0xFFE7AE)              // glow and interrupt flash
  static let coreSpeaking = hex(0x8FD3C9)
  static let coreSpeakingDeep = hex(0x2A8C84)  // non-text only
  static let chipFill = hex(0x0E5E5A)
  static let panelFill = hex(0xF3EFE4).opacity(0.06)
  static let panelBorder = hex(0xF3EFE4).opacity(0.12)
  static let orbPhone: CGFloat = 220
  static let panelWidth: CGFloat = 260
  static let panelHeight: CGFloat = 120
}
