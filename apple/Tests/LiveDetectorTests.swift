import Testing
import Foundation

struct LiveDetectorTests {
  @Test func aPythonTracebackIsFoundByItsLastLine() {
    let text = """
      $ python app.py
      Traceback (most recent call last):
        File "app.py", line 4, in <module>
      TypeError: can only concatenate str (not "float") to str
      """
    let found = LiveDetector.find(in: text)
    #expect(found?.kind == .error)
    #expect(found?.line.hasPrefix("TypeError") == true)
  }

  @Test func compilerErrorsAreFound() {
    #expect(LiveDetector.isError("ContentView.swift:12:5: error: cannot find 'foo' in scope"))
    #expect(LiveDetector.isError("error[E0382]: borrow of moved value: `v`"))
    #expect(LiveDetector.isError("npm ERR! code E404 — tests failed"))
  }

  @Test func ordinaryTextIsNotAnError() {
    #expect(!LiveDetector.isError("Error handling is covered in chapter 4"))
    #expect(!LiveDetector.isError("No errors"))
    #expect(LiveDetector.find(in: "Meeting at 3pm\nBring the slides") == nil)
  }

  @Test func onlyCodingQuestionsAreAnswered() {
    #expect(LiveDetector.isQuestion("How do I reverse a list in Python?"))
    #expect(LiveDetector.isQuestion("Write a function that checks if a string is a palindrome?"))
    #expect(!LiveDetector.isQuestion("Are you coming to dinner tonight?"))
    #expect(!LiveDetector.isQuestion("Why?"))
  }

  @Test func theSameErrorHasTheSameKeyWhateverTheLineNumber() {
    let a = LiveDetector.find(in: "main.swift:10: error: value of optional type must be unwrapped")
    let b = LiveDetector.find(in: "main.swift:12: error: value of optional type must be unwrapped")
    #expect(a?.key == b?.key)
  }
}
