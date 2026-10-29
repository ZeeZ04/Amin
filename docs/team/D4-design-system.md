# Amin design system (D4)

One source of truth for web (`amin/web/app.css`), Apple (`apple/Sources/Kit`) and Android (later). Brand stays: Emirati-door teal, keyhole saffron, sand. Everything below is local (no web fonts, no CDN). Ratios were computed with the WCAG 2.x formula.

## 1. Colour roles
Text needs 4.5:1 (UI and large text 3:1). Values: light / dark / Increase Contrast light / dark.

| Role | Light | Dark | HC light | HC dark |
|---|---|---|---|---|
| bg | F7F8F6 | 0D1615 | FFFFFF | 000000 |
| surface | FFFFFF | 131E1D | FFFFFF | 0D1615 |
| ink | 142826 | E5EDEB | 0A1514 | FFFFFF |
| ink-2 | 3C504D | C3D0CD | 142826 | FFFFFF |
| muted | 5F706D | 8FA19E | 3C504D | C3D0CD |
| accent fill (+on-accent) | 0E5E5A (FFFFFF) | 1F7A72 (FFFFFF) | 0A3F3C (FFFFFF) | 9BE0D6 (0D1615) |
| accent ink (teal text) | 0E5E5A | 6CC5BA | 0A3F3C | 9BE0D6 |
| focus ring | 0E5E5A | E3A72F | 0A3F3C | FFD166 |
| danger | A2322B | EC8A80 | 7E1F1A | FFB3AB |
| line / line-strong | E0E6E3 / 8A9895 | 22312F / 5E726F | 5F706D / 3C504D | 8FA19E / C3D0CD |

Checked ratios: ink on bg 14.5 / 15.4 / 17.4 / 18.4. Muted on surface 5.2 / 6.3 / 8.6 / 10.7. Accent ink on surface 7.6 / 8.4 / 11.7 / 11.4. Danger on surface 6.9 / 6.9 / 10.0 / 10.0. Saffron-ink 3A2A05 on saffron 6.5. Accent-ink on wash 6.4 / 6.5 / 9.0 / 6.9. Control borders (line-strong on surface) 3.0 / 3.3 / 5.2 / 6.3.

**Fixes to existing tokens:**
- Dark `--teal` 2A8C84 with white text is only 4.05. Use **1F7A72** for filled buttons (5.14) and keep 2A8C84 for non-text.
- Saffron on white is 2.14, so it can never be a light-mode focus ring or text. Light focus ring is teal; saffron is dark-mode focus and decoration only.
- Muted on teal-wash is 4.43: use ink-2 there.
- Hairline `--line` is decorative; borders that identify a control (composer, chips) use line-strong.

Rule: never convey state by colour alone (pair with an icon or label).

## 2. Typography
Latin: SF Pro. Arabic: SF Arabic (system picks per glyph; web falls to Noto Sans Arabic, Android to Noto Naskh/Roboto). Malayalam: bundled Noto Sans Malayalam (OFL) everywhere, so it matches on every device.

| Role | Size/weight (Large) | Dynamic Type | Latin LH | Arabic LH | Malayalam LH |
|---|---|---|---|---|---|
| Title | 22 semibold | title2 | 1.25 | 1.4 | 1.55 |
| Headline | 17 semibold | headline | 1.3 | 1.45 | 1.6 |
| Body / answer | 17 | body | 1.45 | 1.65 | 1.75 |
| Callout | 16 | callout | 1.4 | 1.6 | 1.7 |
| Caption / chip | 12 | caption | 1.3 | 1.45 | 1.55 |

Arabic and Malayalam need extra leading (diacritics, stacked conjuncts); the Swift tokens add 12 % and 22 % of font size. Do not letter-space Arabic or Malayalam (breaks joining). Malayalam renders about 1 pt optically smaller: keep minimum 13 pt. Body measure 46rem, about 70 Latin characters. Support up to AX5; layouts reflow, never truncate answers. Mono (citations, code): SF Mono.

## 3. Spacing, radii, elevation
- Spacing, 4-pt grid: 2, 4, 8, 12, 16, 24, 32, 48. Logical (start/end) edges only, so Arabic mirrors. Touch target at least 44 (visionOS 60, tvOS 66).
- Radii: 8 chips, 12 buttons and fields, 16 cards, 22 composer and sheets. Orb and avatars are circles.
- Elevation: three levels, `--shadow-sm/md/lg` as in app.css. Level 0 flat cards use a 1 px line. md for composer and popovers, lg for sheets. In dark mode, use lighter surface (raised) plus line instead of relying on shadows. Vision Pro uses glass materials, not shadows.

## 4. Iconography (SF Symbols, regular weight, hierarchical)
Chat `bubble.left.and.bubble.right`; new chat `square.and.pencil`; send `arrow.up.circle.fill`; stop `stop.circle.fill`; voice orb `waveform` (idle `mic.fill`); documents `doc.text`; projects `folder`; memory `brain.head.profile`; citation `quote.opening`; source `doc.text.magnifyingglass`; private/on-device `lock.shield`; settings `gearshape`; delete `trash`; copy `doc.on.doc`; speak `speaker.wave.2`; warning `exclamationmark.triangle`. Directional symbols (`arrow.backward`, `chevron.forward`) mirror in RTL; `waveform`, `play` do not. Android: Material Symbols equivalents at the same weight; web: inline SVG with `currentColor`.

## 5. Motion
Durations: 150 ms press/hover, 250 ms state change, 400 ms panels. Curves: ease-out `cubic-bezier(.22,1,.36,1)` for entering, ease-in-out for moves. Springs: response 0.35, damping 0.85 (UI); response 0.45, damping 0.7 (orb only). Orb breathes at 4 s idle, scales with voice level (60 fps, transform and opacity only). Streamed answer text fades in per sentence, never per character.
**Reduced motion:** replace springs and scale with 150 ms cross-fades; orb becomes a static ring with a level-bar; no parallax; keep progress visible. Honour `prefers-reduced-motion` and `accessibilityReduceMotion`.

## 6. Components
- **Answer card:** surface, 16 radius, line border, 16 padding. Body text, citation chips inline at end of each claim, action row (copy, speak). A claim without a source shows "No source in your documents" in muted text with a warning icon.
- **Citation chip:** 12 pt caption, 8 radius, accent-wash fill, accent-ink text, number plus short title, 44 pt hit area via padding. States: default, pressed (accent fill), selected. Opens the source panel.
- **Source panel:** inspector 400 pt on web, sidebar on Mac/iPad, sheet on iPhone. Title, file path, highlighted passage (saffron-wash 25 % background, ink text), "Open document". Escape or swipe closes; focus returns to the chip.
- **Composer:** 22 radius, line-strong border, md shadow, min 44 high, grows to 6 lines. Send is accent fill and disabled when empty. Mic button on the trailing end.
- **Voice orb button:** circle at least 64 (HUD: fills screen, teal with saffron core echoing the keyhole). States: idle, listening, thinking (slow rotation), speaking (level-reactive). Label announces the state to VoiceOver ("Listening").
- **Memory row:** icon, memory text (2 lines max), date muted, trailing delete with confirmation. Swipe to delete on touch. Shows "Only on this device".
- **Empty state:** DoorMark 64 pt in accent-ink, one-sentence headline, one-line help, one primary action. Never a blank panel.

## 7. Voice and tone
Amin is calm, direct, trustworthy, never chatty or salesy. Say what is known, from where, and what is not. Admit uncertainty plainly. Privacy is stated as fact ("Stays on your device"), not marketing. No exclamation marks, no emoji, no blame in errors: say what happened and the next step.
- **English:** British spelling, sentence case, short verbs ("Add a document"). "I can't find that in your documents."
- **Arabic:** Modern Standard Arabic, plain and respectful (second person masculine/feminine neutral phrasing preferred, use the infinitive or imperative). Do not machine-translate idioms. Latin numerals only if the user's locale uses them; otherwise follow locale digits. Keep citation numbers and file names as LTR runs inside RTL text (use isolates).
- **Malayalam:** Standard written Malayalam, polite (നിങ്ങൾ), avoid heavy Sanskritised terms; keep common technical words (document, memory) transliterated when users say them. Check conjuncts render. Have a native speaker review all copy before release.

## 8. Swift tokens
Paste as `apple/Sources/Kit/DesignSystem.swift`. Typechecked on macOS SDK. It adds `aminBg/aminInk/...` colours (adaptive for light, dark and Increase Contrast), `Font.amin(_:script:)`, `AminSpace`, `AminRadius`, `AminMotion`. Existing Theme.swift names are untouched. Add the Noto font to the app bundle and `UIAppFonts`.

```swift
import SwiftUI
#if canImport(UIKit) && !os(watchOS)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// Amin design system tokens. Source of truth: docs/team/D4-design-system.md.
// Mirrors amin/web/app.css :root. Brand colours (aminTeal, aminSaffron...) stay in Theme.swift.

private func hex(_ v: UInt32) -> Color {
  Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255, blue: Double(v & 0xFF) / 255)
}

/// Light, dark, and Increase Contrast variants of each role. watchOS is always dark.
private func role(_ l: UInt32, _ d: UInt32, lHC: UInt32, dHC: UInt32) -> Color {
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
}

enum AminMotion {
  static let quick = 0.15        // press, hover
  static let standard = 0.25     // state change
  static let slow = 0.40         // panel, sheet
  static let spring = Animation.spring(response: 0.35, dampingFraction: 0.85)
  static let bouncy = Animation.spring(response: 0.45, dampingFraction: 0.7)  // orb only
  static func adaptive(_ reduceMotion: Bool, _ a: Animation = spring) -> Animation? {
    reduceMotion ? .easeInOut(duration: quick) : a
  }
}
```
