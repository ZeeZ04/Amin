"""Post-training Amin's own model (ADR-012).

    corpus       synthetic household documents + graded questions, disjoint
                 from the eval set by construction and by test
    distill      the teacher (answer_model) runs the real pipeline; only answers
                 the grader passes become supervised examples
    preferences  the tuned student is sampled; what the grader fails becomes the
                 `rejected` side of a preference pair

Facts never go into the weights. Every example is a passage-grounded prompt,
built by the same `answer_prompt()` the pipeline uses at inference time, so
what the student learns is how to read passages, cite and refuse.
"""
