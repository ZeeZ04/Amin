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
          LazyVStack(alignment: .leading, spacing: 24) {
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

  private var composer: some View {
    HStack(alignment: .bottom, spacing: 8) {
      TextField("Message Amin", text: $draft, axis: .vertical)
        .lineLimit(1...6)
        .focused($composing)
        .onSubmit(send)
        .padding(.vertical, 10).padding(.horizontal, 14)
      #if os(iOS) || os(macOS) || os(visionOS)
      Button { voice = true } label: { Image(systemName: "mic").font(.title3) }
        .buttonStyle(.plain).foregroundStyle(.secondary)
        .padding(.bottom, 10)
        .accessibilityLabel("Talk to Amin")
      #endif
      Button(action: send) {
        Image(systemName: "arrow.up.circle.fill").font(.system(size: 32))
      }
      .buttonStyle(.plain)
      .foregroundStyle(draft.trimmingCharacters(in: .whitespaces).isEmpty || model.isBusy ? Color.secondary.opacity(0.4) : .aminTeal)
      .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || model.isBusy)
      .padding(.bottom, 4).padding(.trailing, 4)
      .returnKeySends()
      .accessibilityLabel("Send")
    }
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(.separator))
    .frame(maxWidth: 760)
    .padding(.horizontal, 16).padding(.bottom, 10).padding(.top, 6)
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

  private let starters: [(String, String)] = [
    ("Your documents", "When does our tenancy end?"),
    ("مستنداتك", "كم يوماً لدي لدفع فاتورة الكهرباء؟"),
    ("പൊതുവിജ്ഞാനം", "കേരളത്തിലെ ഏറ്റവും നീളം കൂടിയ നദി ഏതാണ്?"),
  ]

  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      DoorMark().frame(width: 44, height: 44)
      Text("\(greeting), \(model.me?.name ?? "").").font(.largeTitle.bold())
      Text(model.project.map { "Asking in “\($0.name)”. Answers come from its documents first, with the passage shown." }
           ?? "Ask anything. When your documents hold the answer, Amin shows you the passage it came from.")
        .foregroundStyle(.secondary)
      #if os(tvOS)
      VStack(spacing: 12) { starterButtons }
      #else
      ViewThatFits(in: .horizontal) {
        HStack(alignment: .top, spacing: 12) { starterButtons }
        VStack(spacing: 10) { starterButtons }
      }
      #endif
      Label("Runs on your Amin computer. Nothing you ask leaves it.", systemImage: "lock")
        .font(.footnote).foregroundStyle(.secondary)
    }
    .padding(24)
    .frame(maxWidth: 760, alignment: .leading)
    .frame(maxWidth: .infinity)
    .padding(.top, 40)
  }

  @ViewBuilder private var starterButtons: some View {
    ForEach(starters, id: \.1) { label, question in
      Button { ask(question) } label: {
        VStack(alignment: .leading, spacing: 6) {
          Text(label).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
          Text(question).multilineTextAlignment(.leading)
        }
        .frame(maxWidth: .infinity, minHeight: 64, alignment: .topLeading)
        .padding(14)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
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
    VStack(alignment: .leading, spacing: 14) {
      Text(turn.question)
        .padding(.vertical, 10).padding(.horizontal, 16)
        .background(Color.aminTeal.opacity(0.12), in: UnevenRoundedRectangle(
          topLeadingRadius: 20, bottomLeadingRadius: 20, bottomTrailingRadius: 6, topTrailingRadius: 20, style: .continuous))
        .frame(maxWidth: .infinity, alignment: .trailing)
        .selectable()

      HStack(alignment: .top, spacing: 12) {
        DoorMark(tint: .aminSand)
          .padding(5)
          .frame(width: 30, height: 30)
          .background(Color.aminTealDeep, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        if let answer = turn.answer {
          AnswerView(answer: answer, openSource: openSource)
        } else if let failed = turn.failed {
          Label(failed, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
        } else {
          HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Reading…").foregroundStyle(.secondary) }
            .padding(.top, 4)
        }
      }
    }
  }
}

struct AnswerView: View {
  let answer: Answer
  let openSource: (String, Int) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      if let asked = answer.askedAs, !asked.isEmpty {
        Text("Understood as: \(asked)").font(.caption).foregroundStyle(.secondary)
      }
      basis
      Text(body(answer)).font(.body).lineSpacing(3).selectable()
      if !answer.citationOrder.isEmpty && !answer.isGeneral {
        FlowChips(ids: answer.citationOrder, sources: answer.sources ?? [:], open: openSource)
      }
      HStack(spacing: 12) {
        #if !os(tvOS)
        ShareLink(item: answer.text) { Image(systemName: "square.and.arrow.up") }
          .buttonStyle(.plain).foregroundStyle(.secondary)
        #endif
        Text(Duration.milliseconds(answer.latencyMs), format: .units(allowed: [.seconds], fractionalPart: .show(length: 1)))
          .font(.caption).monospacedDigit().foregroundStyle(.secondary)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  @ViewBuilder private var basis: some View {
    if answer.isRemembered {
      Label("Saved to your memory", systemImage: "brain")
        .font(.caption.weight(.semibold)).foregroundStyle(Color.aminTeal)
    } else if answer.claims.isEmpty {
      Label(answer.routedTo != nil ? "Better asked elsewhere" : "No answer", systemImage: "shield")
        .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
    } else if answer.isConflict {
      Label("Your documents disagree on this", systemImage: "exclamationmark.triangle")
        .font(.caption.weight(.semibold)).foregroundStyle(.red)
    } else if answer.isGeneral {
      Label("General knowledge · not from your documents", systemImage: "globe")
        .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
    } else {
      let n = answer.citationOrder.count
      Label("From your documents · \(n) source\(n == 1 ? "" : "s")", systemImage: "doc.text")
        .font(.caption.weight(.semibold)).foregroundStyle(Color.aminTeal)
    }
  }

  /// Claims with their citation numbers inline, in saffron.
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
        var tag = AttributedString(" \(n + 1)")
        tag.foregroundColor = .aminSaffron
        tag.font = .caption.bold()
        tag.baselineOffset = 5
        out += tag
      }
    }
    return out
  }
}

struct FlowChips: View {
  let ids: [String]
  let sources: [String: SourceRef]
  let open: (String, Int) -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 6) {
        ForEach(Array(ids.enumerated()), id: \.element) { i, id in
          Button { open(id, i + 1) } label: {
            HStack(spacing: 6) {
              Text("\(i + 1)").font(.caption2.bold()).frame(minWidth: 18, minHeight: 18)
                .background(Color.aminSaffron.opacity(0.3), in: RoundedRectangle(cornerRadius: 5))
              Text(label(id)).font(.caption).lineLimit(1)
            }
            .padding(.vertical, 5).padding(.leading, 5).padding(.trailing, 10)
            .background(.background.secondary, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
          }
          .buttonStyle(.plain)
        }
      }
    }
  }

  private func label(_ id: String) -> String {
    let doc = String(id.split(separator: "#").first ?? Substring(id))
    let file = doc == "p.memory.md" ? "Your memory" : Chunk(docId: doc, heading: "", text: "").library.file
    guard let h = sources[id]?.heading, !h.isEmpty else { return file }
    return "\(file) · \(h)"
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
            .background(Color.aminSaffron.opacity(0.1), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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
