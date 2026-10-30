import SwiftUI

// Lantern Majlis building blocks (docs/team/D5-in-app-refresh.md §5–6): the
// door panel that carries the brand on every screen, the lantern that glows
// while Amin thinks, and the trust bar that says where an answer came from.

/// A rectangle whose top corners are a full arch, like a majlis door.
struct ArchShape: Shape {
  var bottomRadius: CGFloat = 20  // AminRadius.lg; a Shape is nonisolated
  func path(in r: CGRect) -> Path {
    let top = min(r.width / 2, r.height * 0.45)
    var p = Path()
    p.move(to: CGPoint(x: r.minX, y: r.maxY - bottomRadius))
    p.addLine(to: CGPoint(x: r.minX, y: r.minY + top))
    p.addArc(center: CGPoint(x: r.minX + top, y: r.minY + top), radius: top, startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
    p.addLine(to: CGPoint(x: r.maxX - top, y: r.minY))
    p.addArc(center: CGPoint(x: r.maxX - top, y: r.minY + top), radius: top, startAngle: .degrees(270), endAngle: .degrees(0), clockwise: false)
    p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - bottomRadius))
    p.addArc(center: CGPoint(x: r.maxX - bottomRadius, y: r.maxY - bottomRadius), radius: bottomRadius, startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
    p.addLine(to: CGPoint(x: r.minX + bottomRadius, y: r.maxY))
    p.addArc(center: CGPoint(x: r.minX + bottomRadius, y: r.maxY - bottomRadius), radius: bottomRadius, startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
    p.closeSubpath()
    return p
  }
}

/// The deep-teal door panel: brass-stud lattice at 4% sand, a 1 pt highlight
/// along the top, and a lantern glow behind whatever it holds. Static, cheap.
struct DoorPanel<Content: View>: View {
  var arch = true
  var glow = true
  @ViewBuilder var content: Content

  var body: some View {
    let shape = arch ? AnyShape(ArchShape()) : AnyShape(RoundedRectangle(cornerRadius: AminRadius.lg))
    content
      .frame(maxWidth: .infinity)
      .background {
        ZStack {
          Color.aminDoor
          if glow {
            RadialGradient(colors: [Color.aminLantern.opacity(0.32), .clear], center: .center, startRadius: 0, endRadius: 170)
          }
          StudLattice().opacity(0.06)
        }
        .clipShape(shape)
        .overlay(shape.stroke(Color.aminOnDoor.opacity(0.12), lineWidth: 1))
      }
      .shadow(color: Color.aminDoor.opacity(0.10), radius: 18, y: 6)
  }
}

/// A quiet grid of brass studs, as on a carved door. At most ~60 dots.
struct StudLattice: View {
  var body: some View {
    Canvas { ctx, size in
      let step = max(size.width, size.height) / 8
      var y = step / 2
      var row = 0
      while y < size.height {
        var x = row.isMultiple(of: 2) ? step / 2 : step
        while x < size.width {
          ctx.fill(Path(ellipseIn: CGRect(x: x - 2, y: y - 2, width: 4, height: 4)), with: .color(Color.aminOnDoor))
          x += step
        }
        y += step; row += 1
      }
    }
    .allowsHitTesting(false)
    .accessibilityHidden(true)
  }
}

/// The saffron lantern dot that breathes while Amin is thinking (replaces a spinner).
struct LanternDot: View {
  var size: CGFloat = 12
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var lit = false

  var body: some View {
    Circle().fill(Color.aminLantern)
      .frame(width: size, height: size)
      .shadow(color: Color.aminLantern.opacity(lit ? 0.8 : 0.2), radius: lit ? size : size / 3)
      .opacity(reduceMotion ? 1 : (lit ? 1 : 0.55))
      .onAppear {
        guard !reduceMotion else { return }
        withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) { lit = true }
      }
      .accessibilityHidden(true)
  }
}

/// Where an answer came from, said at full width (D5: the product's promise, not a caption).
struct TrustBar: View {
  enum Kind { case documents, general, conflict, failed }
  let kind: Kind
  let text: String

  var body: some View {
    Label { Text(text).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: icon) }
      .font(.aminTrust)
      .foregroundStyle(ink)
      .padding(.horizontal, AminSpace.md)
      .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
      .background(fill, in: RoundedRectangle(cornerRadius: AminRadius.sm))
  }

  private var icon: String {
    switch kind {
    case .documents: "doc.text.magnifyingglass"
    case .general: "globe"
    case .conflict: "exclamationmark.triangle"
    case .failed: "xmark.octagon"
    }
  }
  private var fill: Color {
    switch kind {
    case .documents: .aminAccentWash
    case .general: .aminSidebar
    case .conflict: .aminWashGold
    case .failed: .aminDangerWash
    }
  }
  private var ink: Color {
    switch kind {
    case .documents: .aminAccentInk
    case .general: .aminInk2
    case .conflict: .aminLanternInk
    case .failed: .aminDanger
    }
  }
}

extension View {
  /// D5 field: 52 pt tall, radius 14, surface fill, strong border.
  @ViewBuilder func aminField() -> some View {
    #if os(tvOS)
    self
    #else
    self.textFieldStyle(.plain)
      .padding(.horizontal, AminSpace.md)
      .frame(minHeight: 52)
      .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.md))
      .overlay(RoundedRectangle(cornerRadius: AminRadius.md).strokeBorder(Color.aminLineStrong.opacity(0.6)))
    #endif
  }
}
