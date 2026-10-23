import SwiftUI
import UniformTypeIdentifiers
#if os(iOS)
import VisionKit
#endif

// MARK: - documents

struct DocumentsView: View {
  @Environment(AppModel.self) private var model
  @State private var library: Library = .mine
  @State private var importing = false
  @State private var scanning = false
  @State private var status: String?
  @State private var working = false

  private var files: [String] {
    switch library {
    case .mine: model.me?.private ?? []
    case .household: model.me?.household ?? []
    case .project(let id): model.me?.projects.first { $0.id == id }?.documents ?? []
    }
  }
  private var canDelete: Bool {
    switch library {
    case .mine: true
    case .household: model.me?.admin == true
    case .project(let id): model.me?.projects.first { $0.id == id }?.isOwner == true
    }
  }

  var body: some View {
    List {
      Section {
        Picker("Library", selection: $library) {
          Text("Only me").tag(Library.mine)
          Text("Household").tag(Library.household)
          ForEach(model.me?.projects ?? []) { Text($0.name).tag(Library.project($0.id)) }
        }
        #if !os(tvOS)
        HStack {
          Button("Choose a file", systemImage: "doc.badge.plus") { importing = true }
          #if os(iOS)
          if VNDocumentCameraViewController.isSupported {
            Spacer()
            Button("Scan", systemImage: "doc.viewfinder") { scanning = true }
          }
          #endif
        }
        .buttonStyle(.borderless)
        .disabled(working)
        #endif
        if working { ProgressView("Reading the text…") }
        if let status { Text(status).font(.callout).foregroundStyle(.secondary) }
      } footer: {
        Text("PDF, text, Markdown, HTML or a photo, in English, Arabic or Malayalam. Kept on your Amin computer only.")
      }

      Section(files.isEmpty ? "" : "\(files.count) document\(files.count == 1 ? "" : "s")") {
        if files.isEmpty {
          ContentUnavailableView("No documents yet", systemImage: "doc", description: Text("Add one and ask about it straight away."))
        }
        ForEach(files, id: \.self) { f in
          Label(f, systemImage: icon(f))
            #if !os(tvOS)
            .swipeActions { if canDelete { Button("Delete", systemImage: "trash", role: .destructive) { remove(f) } } }
            #endif
            .contextMenu { if canDelete { Button("Delete", systemImage: "trash", role: .destructive) { remove(f) } } }
        }
      }
    }
    .navigationTitle("Documents")
    #if !os(tvOS)
    .fileImporter(isPresented: $importing, allowedContentTypes: [.pdf, .plainText, .html, .image, UTType(filenameExtension: "md") ?? .plainText]) { result in
      guard case .success(let url) = result else { return }
      let ok = url.startAccessingSecurityScopedResource()
      defer { if ok { url.stopAccessingSecurityScopedResource() } }
      if let data = try? Data(contentsOf: url) { upload(data, name: url.lastPathComponent) }
    }
    #endif
    #if os(iOS)
    .fullScreenCover(isPresented: $scanning) {
      DocumentScanner { pdf in
        scanning = false
        if let pdf { upload(pdf, name: "scan-\(Date.now.formatted(.iso8601.year().month().day().time(includingFractionalSeconds: false))).pdf".replacingOccurrences(of: ":", with: "-")) }
      }
      .ignoresSafeArea()
    }
    #endif
    .refreshable { try? await model.refresh() }
  }

  private func icon(_ f: String) -> String {
    switch (f as NSString).pathExtension.lowercased() {
    case "pdf": "doc.richtext"
    case "jpg", "jpeg", "png", "heic": "photo"
    default: "doc.text"
    }
  }

  private func upload(_ data: Data, name: String) {
    guard let client = model.client else { return }
    working = true; status = nil
    Task {
      defer { working = false }
      do {
        let r = try await client.upload(data, filename: name, to: library)
        status = "Saved \(r.document). You can ask about it now."
        try? await model.refresh()
      } catch { status = error.localizedDescription }
    }
  }

  private func remove(_ f: String) {
    Task {
      do { try await model.client?.delete(f, from: library); try? await model.refresh() }
      catch { model.error = error.localizedDescription }
    }
  }
}

#if os(iOS)
/// VisionKit's document camera; pages become one PDF, which Amin OCRs.
struct DocumentScanner: UIViewControllerRepresentable {
  let done: (Data?) -> Void

  func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
    let vc = VNDocumentCameraViewController()
    vc.delegate = context.coordinator
    return vc
  }
  func updateUIViewController(_ vc: VNDocumentCameraViewController, context: Context) {}
  func makeCoordinator() -> Coordinator { Coordinator(done: done) }

  final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
    let done: (Data?) -> Void
    init(done: @escaping (Data?) -> Void) { self.done = done }

    func documentCameraViewController(_ c: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
      let bounds = CGRect(x: 0, y: 0, width: 612, height: 792)  // US Letter at 72 dpi; pages are aspect-fitted
      let pdf = UIGraphicsPDFRenderer(bounds: bounds).pdfData { ctx in
        for i in 0..<scan.pageCount {
          ctx.beginPage()
          let img = scan.imageOfPage(at: i)
          let scale = min(bounds.width / img.size.width, bounds.height / img.size.height)
          let size = CGSize(width: img.size.width * scale, height: img.size.height * scale)
          img.draw(in: CGRect(origin: CGPoint(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2), size: size))
        }
      }
      done(pdf)
    }
    func documentCameraViewControllerDidCancel(_ c: VNDocumentCameraViewController) { done(nil) }
    func documentCameraViewController(_ c: VNDocumentCameraViewController, didFailWithError e: Error) { done(nil) }
  }
}
#endif

// MARK: - projects

struct ProjectsView: View {
  @Environment(AppModel.self) private var model
  let onAsk: (String) -> Void
  @State private var naming = false
  @State private var newName = ""

  var body: some View {
    List {
      if (model.me?.projects ?? []).isEmpty {
        ContentUnavailableView("No projects yet", systemImage: "folder",
                               description: Text("Keep a set of documents together: a flat, a car, a school year."))
      }
      ForEach(model.me?.projects ?? []) { p in
        NavigationLink {
          ProjectDetail(project: p, onAsk: onAsk)
        } label: {
          VStack(alignment: .leading, spacing: 2) {
            Text(p.name)
            Text(p.isOwner ? "\(p.documents.count) document\(p.documents.count == 1 ? "" : "s")"
                 : "Shared by \(p.owner)").font(.caption).foregroundStyle(.secondary)
          }
        }
      }
    }
    .navigationTitle("Projects")
    .toolbar { Button("New project", systemImage: "plus") { naming = true } }
    .alert("New project", isPresented: $naming) {
      TextField("Flat in Marina", text: $newName)
      Button("Create") { create() }
      Button("Cancel", role: .cancel) { newName = "" }
    } message: { Text("A project keeps its own documents. Answers in it come from them first.") }
  }

  private func create() {
    let name = newName; newName = ""
    Task {
      do { _ = try await model.client?.createProject(name); try await model.refresh() }
      catch { model.error = error.localizedDescription }
    }
  }
}

struct ProjectDetail: View {
  @Environment(AppModel.self) private var model
  @Environment(\.dismiss) private var dismiss
  let project: Project
  let onAsk: (String) -> Void
  @State private var confirmDelete = false

  var body: some View {
    List {
      Section {
        Button("Ask in this project", systemImage: "bubble.left") { onAsk(project.id) }
      } footer: {
        Text(project.isOwner ? (project.members.isEmpty ? "Only you can see this project." : "Shared with \(project.members.joined(separator: ", ")).")
             : "Shared with you by \(project.owner).")
      }
      Section("Documents") {
        if project.documents.isEmpty { Text("No documents yet. Add them from Documents.").foregroundStyle(.secondary) }
        ForEach(project.documents, id: \.self) { Label($0, systemImage: "doc.text") }
      }
      if project.isOwner {
        Section {
          Button("Delete project", role: .destructive) { confirmDelete = true }
        } footer: { Text("Permissions and sharing are managed in the web app for now.") }
      }
    }
    .navigationTitle(project.name)
    .confirmationDialog("Delete “\(project.name)”?", isPresented: $confirmDelete, titleVisibility: .visible) {
      Button("Delete project", role: .destructive) {
        Task {
          try? await model.client?.deleteProject(project.id)
          try? await model.refresh()
          dismiss()
        }
      }
    } message: { Text("Its documents and conversations are removed from your Amin computer.") }
  }
}
