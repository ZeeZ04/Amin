import Foundation
import Testing

/// The on-device library: the server's chunking and evidence floor, ported.
struct LocalLibraryTests {
  func library(_ files: [String: String]) throws -> LocalLibrary {
    let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let lib = try LocalLibrary(url: dir.appending(path: "lib.db"))
    for (name, text) in files {
      let f = dir.appending(path: name)
      try text.write(to: f, atomically: true, encoding: .utf8)
      try lib.add(f)
    }
    return lib
  }

  @Test func findsThePassageAndCitesIt() throws {
    let lib = try library([
      "fridge.md": "# Warranty\nThe ArcticLine FR-440 has a 24-month warranty. The sealed cooling system is covered for 60 months.",
      "lease.md": "# Rent\nRent is due on the first of each month. The deposit is 1,200 pounds.",
    ])
    let hits = lib.search("How long is the fridge warranty?")
    #expect(hits.first?.chunk.docId == "p.fridge.md")
    let claims = Grounded.claims("The FR-440 has a 24-month warranty [S1]. It is covered for 99 months [S1].", hits)
    // The second sentence states a number its passage does not contain, so it is dropped.
    #expect(claims.map(\.text) == ["The FR-440 has a 24-month warranty."])
    #expect(claims.first?.citations == [hits[0].chunkId])
    #expect(lib.chunk(hits[0].chunkId)?.text.contains("60 months") == true)
  }

  @Test func saysNothingWhenTheLibraryDoesNotCoverTheQuestion() throws {
    let lib = try library(["fridge.md": "The ArcticLine FR-440 has a 24-month warranty."])
    #expect(lib.search("When is my daughter's piano recital?").isEmpty)
    #expect(Grounded.claims("NO_EVIDENCE", lib.search("fridge warranty")).isEmpty)
  }

  @Test func malayalamAndArabicAreSearchable() throws {
    let lib = try library([
      "ml.md": "വാടക എല്ലാ മാസവും ഒന്നാം തീയതി അടയ്ക്കണം.",
      "ar.md": "يجب دفع الإيجار في اليوم الأول من كل شهر.",
    ])
    #expect(lib.search("വാടക എപ്പോൾ അടയ്ക്കണം?").first?.chunk.docId == "p.ml.md")
    #expect(lib.search("متى يجب دفع الإيجار؟").first?.chunk.docId == "p.ar.md")
  }

  @Test func reAddingAFileReplacesItAndRemoveForgetsIt() throws {
    let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let lib = try LocalLibrary(url: dir.appending(path: "lib.db"))
    let f = dir.appending(path: "note.md")
    try "The boiler code is 4417.".write(to: f, atomically: true, encoding: .utf8); try lib.add(f)
    try "The boiler code is 9902.".write(to: f, atomically: true, encoding: .utf8); try lib.add(f)
    #expect(lib.search("boiler code").map(\.chunk.text) == ["The boiler code is 9902."])
    try lib.remove("p.note.md")
    #expect(lib.search("boiler code").isEmpty && lib.documents().isEmpty)
  }

  @Test func oversizedTablesAreSplit() {
    let table = (0..<400).map { "| row \($0) | " + String(repeating: "x", count: 60) + " |" }.joined(separator: "\n")
    let pieces = LocalLibrary.pack("Intro.\n\n" + table)
    #expect(pieces.count > 20 && pieces.allSatisfy { $0.count <= 1800 })
  }
}
