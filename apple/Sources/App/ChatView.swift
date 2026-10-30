import SwiftUI

struct ChatView: View {
  @Environment(AppModel.self) private var model
  /// iPhone and Apple TV have no sidebar: history opens from the toolbar.
  var showsHistory = false
  @State private var history = false
  @State private var draft = ""
  @State private var shownSource: SourceRequest?
  @State private var voice = false
  @State private var ambient = false
  @FocusState private var composing: Bool

  struct SourceRequest: Identifiable, Hashable { let id: String; let number: Int }

  var body: some View {
    ScrollViewReader { proxy in
      ScrollView {
        if model.turns.isEmpty {
          Welcome { draft = $0; send() }
        } else {
          LazyVStack(alignment: .leading, spacing: 28) {
            ForEach(model.turns) { turn in
              TurnView(turn: turn) { id, n in shownSource = SourceRequest(id: id, number: n) }
                .id(turn.id)
            }
          }
          .padding(.horizontal, 20).padding(.vertical, 16)
          .frame(maxWidth: 760)
          .frame(maxWidth: .infinity)
        }
      }
      .onChange(of: model.turns.last?.answer) { _, _ in
        if let last = model.turns.last { withAnimation(.snappy) { proxy.scrollTo(last.id, anchor: .bottom) } }
      }
      .onChange(of: model.turns.count) { _, _ in
        if let last = model.turns.last { withAnimation(.snappy) { proxy.scrollTo(last.id, anchor: .bottom) } }
      }
    }
    .background(Color.aminBg.ignoresSafeArea())
    .safeAreaInset(edge: .bottom) { composer }
    .navigationTitle(model.project?.name ?? "Amin")
    #if !os(macOS) && !os(tvOS)
    .navigationBarTitleDisplayMode(.inline)
    #endif
    .toolbar { toolbar }
    .sourceInspector(item: $shownSource)
    .sheet(isPresented: $history) { HistorySheet() }
    #if os(iOS)
    .fullScreenCover(isPresented: $ambient) { AmbientView() }
    #endif
    #if os(iOS) || os(macOS) || os(visionOS)
    .fullScreenCoverCompat(isPresented: $voice) { VoiceView() }
    #endif
  }

  @ToolbarContentBuilder private var toolbar: some ToolbarContent {
    if showsHistory {
      ToolbarItem(placement: .navigation) {
        Button("History", systemImage: "clock.arrow.circlepath") { history = true }
      }
    }
    ToolbarItem(placement: .principal) { SpaceMenu() }
    ToolbarItem(placement: .primaryAction) {
      Button("New chat", systemImage: "square.and.pencil") { model.newChat() }
        .disabled(model.turns.isEmpty)
    }
    #if os(iOS)
    ToolbarItem(placement: .primaryAction) {
      Button("Ambient mode", systemImage: "circle.hexagongrid") { ambient = true }
    }
    #endif
  }

  /// D5 composer: a glass capsule; the mic is Amin's primary action, send glows lantern-gold when ready.
  private var composer: some View {
    let empty = draft.trimmingCharacters(in: .whitespaces).isEmpty || model.isBusy
    return HStack(alignment: .bottom, spacing: AminSpace.sm) {
      TextField("Message Amin", text: $draft, axis: .vertical)
        .lineLimit(1...6)
        .focused($composing)
        .onSubmit(send)
        .font(.aminBody)
        .padding(.vertical, 14).padding(.leading, 18)
      #if os(iOS) || os(macOS) || os(visionOS)
      Button { voice = true } label: {
        Image(systemName: "mic.fill").font(.system(size: 18, weight: .semibold))
          .foregroundStyle(Color.aminAccentInk)
          .frame(width: 44, height: 44)
          .background(Color.aminAccentWash, in: Circle())
      }
      .buttonStyle(.plain)
      .padding(.bottom, 4)
      .accessibilityLabel("Talk to Amin")
      #endif
      Button(action: send) {
        Image(systemName: "arrow.up").font(.system(size: 18, weight: .bold))
          .foregroundStyle(empty ? Color.aminMuted : Color.aminOnGold)
          .frame(width: 44, height: 44)
          .background(empty ? Color.aminLine.opacity(0.7) : Color.aminLantern, in: Circle())
          .shadow(color: empty ? .clear : Color.aminLantern.opacity(0.45), radius: 8)
      }
      .buttonStyle(.plain)
      .disabled(empty)
      .padding(.bottom, 4).padding(.trailing, 4)
      .returnKeySends()
      .accessibilityLabel("Send")
      .animation(AminMotion.spring, value: empty)
    }
    .frame(minHeight: 52)
    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: AminRadius.xl, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: AminRadius.xl, style: .continuous).strokeBorder(Color.aminLine))
    .frame(maxWidth: 760)
    .padding(.horizontal, AminSpace.lg).padding(.bottom, 10).padding(.top, 6)
  }

  private func send() {
    let q = draft
    guard !q.trimmingCharacters(in: .whitespaces).isEmpty else { return }
    draft = ""
    Task { await model.ask(q) }
  }
}

// MARK: - pieces

struct SpaceMenu: View {
  @Environment(AppModel.self) private var model

  var body: some View {
    Menu {
      Picker("Ask in", selection: Binding(get: { model.space }, set: { model.newChat(in: $0) })) {
        Label("General chat", systemImage: "globe").tag("")
        ForEach(model.me?.projects ?? []) { p in
          Label(p.name, systemImage: "folder").tag(p.id)
        }
      }
    } label: {
      HStack(spacing: 5) {
        Image(systemName: model.project == nil ? "globe" : "folder")
        Text(model.project?.name ?? "General chat").lineLimit(1)
        Image(systemName: "chevron.down").font(.caption2.weight(.bold)).foregroundStyle(.secondary)
      }
      .font(.subheadline.weight(.medium))
      .fixedSize()
    }
  }
}

struct Welcome: View {
  @Environment(AppModel.self) private var model
  let ask: (String) -> Void

  /// Starters by kind (D5: colour-coded): documents in teal, general knowledge in sand.
  private let starters: [(String, String, String, Bool)] = [
    ("Your documents", "When does our tenancy end?", "doc.text", true),
    ("مستنداتك", "كم يوماً لدي لدفع فاتورة الكهرباء؟", "doc.text", true),
    ("പൊതുവിജ്ഞാനം", "കേരളത്തിലെ ഏറ്റവും നീളം കൂടിയ നദി ഏതാണ്?", "globe", false),
  ]

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.xl) {
      DoorPanel {
        DoorMark(tint: .aminOnDoor).frame(width: 72, height: 72)
          .padding(.top, 44).padding(.bottom, AminSpace.xl)
      }
      .frame(width: 220)
      .frame(maxWidth: .infinity)
      VStack(alignment: .leading, spacing: AminSpace.sm) {
        Text(name.isEmpty ? "\(greeting)." : "\(greeting), \(name).").font(.aminDisplay).foregroundStyle(Color.aminInk)
          .fixedSize(horizontal: false, vertical: true)
        Text(model.project.map { "Asking in “\($0.name)”. Answers come from its documents first, with the passage shown." }
             ?? "Ask anything. When your documents hold the answer, Amin shows you the passage it came from.")
          .font(.aminBody).foregroundStyle(Color.aminMuted)
          .fixedSize(horizontal: false, vertical: true)
      }
      #if os(tvOS)
      VStack(spacing: 12) { starterButtons }
      #else
      ViewThatFits(in: .horizontal) {
        HStack(alignment: .top, spacing: AminSpace.md) { starterButtons }
        VStack(spacing: AminSpace.md) { starterButtons }
      }
      #endif
      Label(privacyLine, systemImage: "lock.fill")
        .font(.aminTrust).foregroundStyle(Color.aminAccentInk)
        .padding(.horizontal, AminSpace.md).padding(.vertical, AminSpace.sm)
        .background(Color.aminAccentWash, in: Capsule())
    }
    .padding(AminSpace.xl)
    .frame(maxWidth: 760, alignment: .leading)
    .frame(maxWidth: .infinity)
    .padding(.top, AminSpace.lg)
  }

  private var name: String { model.me?.name ?? accountName ?? "" }
  private var accountName: String? {
    #if os(iOS) || os(macOS) || os(visionOS)
    model.account.displayName
    #else
    nil
    #endif
  }
  private var privacyLine: String {
    model.client == nil ? "On this device · nothing you ask leaves it" : "On your Amin computer · nothing you ask leaves home"
  }

  @ViewBuilder private var starterButtons: some View {
    ForEach(starters, id: \.1) { label, question, icon, docs in
      Button { ask(question) } label: {
        VStack(alignment: .leading, spacing: AminSpace.sm) {
          Label(label, systemImage: icon)
            .font(.aminTrust).foregroundStyle(docs ? Color.aminAccentInk : Color.aminInk2)
          Text(question).font(.aminBody).foregroundStyle(Color.aminInk).multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .topLeading)
        .padding(AminSpace.lg)
        .background(docs ? Color.aminAccentWash : Color.aminSidebar, in: RoundedRectangle(cornerRadius: AminRadius.lg, style: .continuous))
        .environment(\.layoutDirection, question.unicodeScalars.contains { (0x0600...0x06FF).contains($0.value) } ? .rightToLeft : .leftToRight)
      }
      .buttonStyle(.plain)
    }
  }

  private var greeting: String {
    switch Calendar.current.component(.hour, from: .now) {
    case 5..<12: "Good morning"
    case 12..<18: "Good afternoon"
    default: "Good evening"
    }
  }
}

struct TurnView: View {
  let turn: AppModel.Turn
  let openSource: (String, Int) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.md) {
      // Your question, on the door (D5): sand on deep teal, 10:1.
      Text(turn.question)
        .font(.aminBody).foregroundStyle(Color.aminOnDoor)
        .padding(.vertical, 12).padding(.horizontal, 18)
        .background(Color.aminDoor, in: UnevenRoundedRectangle(
          topLeadingRadius: 22, bottomLeadingRadius: 22, bottomTrailingRadius: 6, topTrailingRadius: 22, style: .continuous))
        .frame(maxWidth: .infinity, alignment: .trailing)
        .selectable()

      if let answer = turn.answer {
        AnswerView(answer: answer, openSource: openSource)
          .transition(.opacity.combined(with: .move(edge: .bottom)))
      } else if let failed = turn.failed {
        TrustBar(kind: .failed, text: failed)
      } else {
        HStack(spacing: AminSpace.md) {
          LanternDot()
          Text("Reading…").font(.aminSerif(.body)).foregroundStyle(Color.aminMuted)
        }
        .padding(.vertical, AminSpace.sm)
        .accessibilityElement(children: .combine)
      }
    }
    .animation(AminMotion.spring, value: turn.answer)
  }
}

struct AnswerView: View {
  let answer: Answer
  let openSource: (String, Int) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: AminSpace.md) {
      basis
      if let asked = answer.askedAs, !asked.isEmpty {
        Text("Understood as: \(asked)").font(.aminCaption).foregroundStyle(Color.aminMuted)
      }
      let script = AminScript.of(answer.text)
      Text(body(answer)).font(.aminSerif(.title3, script: script)).foregroundStyle(Color.aminInk)
        .lineSpacing(6 + Font.aminSize(.title3) * script.extraLeading).selectable()
        .fixedSize(horizontal: false, vertical: true)
      if !answer.citationOrder.isEmpty && !answer.isGeneral {
        SourcesStrip(ids: answer.citationOrder, sources: answer.sources ?? [:], open: openSource)
      }
      HStack(spacing: AminSpace.md) {
        #if !os(tvOS)
        ShareLink(item: answer.text) { Image(systemName: "square.and.arrow.up") }
          .buttonStyle(.plain).foregroundStyle(Color.aminMuted)
        #endif
        Spacer()
        Text(Duration.milliseconds(answer.latencyMs), format: .units(allowed: [.seconds], fractionalPart: .show(length: 1)))
          .font(.aminCaption).monospacedDigit().foregroundStyle(Color.aminMuted)
      }
    }
    .padding(20)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Color.aminSurface, in: RoundedRectangle(cornerRadius: AminRadius.lg, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: AminRadius.lg, style: .continuous).strokeBorder(Color.aminLine))
  }

  @ViewBuilder private var basis: some View {
    if answer.isRemembered {
      TrustBar(kind: .documents, text: "Saved to your memory")
    } else if answer.claims.isEmpty {
      TrustBar(kind: .general, text: answer.routedTo != nil ? "Better asked elsewhere" : "No answer in your documents")
    } else if answer.isConflict {
      TrustBar(kind: .conflict, text: "Your documents disagree on this")
    } else if answer.isGeneral {
      TrustBar(kind: .general, text: "General knowledge · not from your documents")
    } else {
      let n = answer.citationOrder.count
      TrustBar(kind: .documents, text: "From your documents · \(n) source\(n == 1 ? "" : "s")")
    }
  }

  /// Claims with their citation numbers inline, as lantern-ink superscripts (≥4.5:1, D5).
  private func body(_ a: Answer) -> AttributedString {
    if a.isRemembered { return AttributedString((a.refusalReason ?? "").replacingOccurrences(of: "Saved to your memory: ", with: "")) }
    guard !a.claims.isEmpty else { return AttributedString(a.refusalReason ?? "") }
    let order = a.citationOrder
    var out = AttributedString()
    for (i, claim) in a.claims.enumerated() {
      out += AttributedString((i == 0 ? "" : " ") + claim.text)
      guard !a.isGeneral else { continue }
      for id in claim.citations {
        guard let n = order.firstIndex(of: id) else { continue }
        var tag = AttributedString("\u{2009}\(n + 1)")
        tag.foregroundColor = .aminLanternInk
        tag.font = .system(.caption, design: .rounded).bold()
        tag.baselineOffset = 6
        out += tag
      }
    }
    return out
  }
}

/// D5 sources strip: a card per cited passage, numbered, with the file and its
/// section; names wrap to two lines instead of truncating to one.
struct SourcesStrip: View {
  let ids: [String]
  let sources: [String: SourceRef]
  let open: (String, Int) -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: AminSpace.sm) {
        ForEach(Array(ids.enumerated()), id: \.element) { i, id in
          Button { open(id, i + 1) } label: {
            HStack(alignment: .top, spacing: AminSpace.sm) {
              Text("\(i + 1)").font(.system(.caption, design: .rounded).bold())
                .foregroundStyle(Color.aminLanternInk)
                .frame(width: 22, height: 22)
                .background(Color.aminWashGold, in: Circle())
              VStack(alignment: .leading, spacing: 2) {
                Text(file(id)).font(.aminCaption.weight(.semibold)).foregroundStyle(Color.aminInk).lineLimit(2)
                if let h = sources[id]?.heading, !h.isEmpty {
                  Text(h).font(.aminCaption).foregroundStyle(Color.aminMuted).lineLimit(1)
                }
              }
            }
            .frame(width: 200, alignment: .leading)
            .frame(minHeight: 44)
            .padding(AminSpace.sm)
            .background(Color.aminBg, in: RoundedRectangle(cornerRadius: AminRadius.md, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: AminRadius.md, style: .continuous).strokeBorder(Color.aminLine))
          }
          .buttonStyle(.plain)
          .accessibilityLabel("Source \(i + 1): \(file(id))")
        }
      }
    }
  }

  private func file(_ id: String) -> String {
    let doc = String(id.split(separator: "#").first ?? Substring(id))
    return doc == "p.memory.md" ? "Your memory" : Chunk(docId: doc, heading: "", text: "").library.file
  }
}

// MARK: - source

struct SourceView: View {
  @Environment(AppModel.self) private var model
  let request: ChatView.SourceRequest
  @State private var chunk: Chunk?
  @State private var failed: String?

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 14) {
        if let chunk {
          let lib = chunk.library
          VStack(alignment: .leading, spacing: 4) {
            Text(lib.file).font(.headline)
            Text(chunk.heading.isEmpty ? lib.name : "\(lib.name) · \(chunk.heading)").font(.subheadline).foregroundStyle(.secondary)
          }
          Text(chunk.text)
            .selectable()
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.aminWashGold, in: RoundedRectangle(cornerRadius: AminRadius.md, style: .continuous))
            .overlay(alignment: .leading) { Capsule().fill(Color.aminLantern).frame(width: 3).padding(.vertical, AminSpace.sm) }
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Color.aminSaffron.opacity(0.35)))
          Text("This is the passage Amin cited. A sentence its passage does not support is removed before you see the answer.")
            .font(.footnote).foregroundStyle(.secondary)
        } else if let failed {
          ContentUnavailableView("Source unavailable", systemImage: "doc.questionmark", description: Text(failed))
        } else {
          ProgressView().frame(maxWidth: .infinity, minHeight: 120)
        }
      }
      .padding(20)
    }
    .navigationTitle("Source \(request.number)")
    .task(id: request) {
      do { chunk = try await model.source(request.id) }
      catch { failed = error.localizedDescription }
    }
  }
}

extension View {
  /// The cited passage: an inspector column on iPad and Mac, a sheet elsewhere.
  @ViewBuilder func sourceInspector(item: Binding<ChatView.SourceRequest?>) -> some View {
    #if os(iOS) || os(macOS)
    self.inspector(isPresented: Binding(get: { item.wrappedValue != nil }, set: { if !$0 { item.wrappedValue = nil } })) {
      if let r = item.wrappedValue {
        NavigationStack { SourceView(request: r) }
          .inspectorColumnWidth(min: 300, ideal: 380, max: 520)
          .presentationDetents([.medium, .large])
      }
    }
    #else
    self.sheet(item: item) { r in NavigationStack { SourceView(request: r) } }
    #endif
  }

  @ViewBuilder func fullScreenCoverCompat<Content: View>(isPresented: Binding<Bool>, @ViewBuilder content: @escaping () -> Content) -> some View {
    #if os(iOS)
    self.fullScreenCover(isPresented: isPresented, content: content)
    #else
    self.sheet(isPresented: isPresented, content: content)
    #endif
  }
}
