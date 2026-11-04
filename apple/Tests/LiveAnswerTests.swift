import Foundation
import Testing

struct LiveAnswerTests {
  @Test func stepsAndCodeAreSplit() {
    let a = LiveAnswer("""
      Steps:
      1. Remove duplicates with a set.
      2. Sort the rest, largest first.
      Answer:
      ```python
      def second_largest(xs):
          s = sorted(set(xs), reverse=True)
          return s[1] if len(s) > 1 else None
      ```
      """)
    #expect(a.steps == ["Remove duplicates with a set.", "Sort the rest, largest first."])
    #expect(a.isCode)
    #expect(a.answer.hasPrefix("def second_largest"))
  }

  @Test func boldHeadingsAndAnInlineAnswerWork() {
    let a = LiveAnswer("**Steps:**\n- Convert the float.\n**Answer:** use float(price)")
    #expect(a.steps == ["Convert the float."])
    #expect(a.answer == "use float(price)")
    #expect(!a.isCode)
  }

  @Test func aReplyWithoutHeadingsIsAllAnswer() {
    let a = LiveAnswer("Use .get('b') instead.")
    #expect(a.steps.isEmpty)
    #expect(a.answer == "Use .get('b') instead.")
  }

  @Test func whileStreamingBeforeTheAnswerOnlyStepsShow() {
    let a = LiveAnswer("Steps:\n1. Read the input")
    #expect(a.steps == ["Read the input"])
  }
}
