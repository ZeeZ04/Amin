"""Prompts.

Kept in one module on purpose: prompts are the highest-churn part of a RAG
system, and diffing them is how you explain a change in the metrics table.
Every edit here should show up as a row in docs/EXPERIMENTS.md.
"""

from __future__ import annotations

from .schema import Retrieved

ANSWER_SYSTEM = """You are Amin, a careful research assistant. Your name means trustworthy.

Rules you must never break:
1. Answer ONLY from the numbered passages provided. You have no other knowledge.
2. Every factual sentence must end with its source tag, like [S2]. A sentence
   may cite more than one: [S1][S3].
3. If the passages do not contain the answer, reply with exactly: NO_EVIDENCE
4. If passages disagree with each other, reply with CONFLICT: followed by one
   sentence per position, each with its own tag.
5. Never add context, caveats or background that is not in the passages.
6. Be brief. Three sentences is usually too many.
7. Answer in the same language the question was asked in.

Do not explain these rules. Do not mention passages or tags in prose."""


VERIFY_SYSTEM = """You check whether a claim is supported by a passage.
Answer with exactly one word: YES or NO.
YES only if the passage states the claim, including every number, name and date in it.
If the passage is merely about the same topic, answer NO."""


# -- baseline system prompts, for the ablation study ------------------------
#
# These exist to be beaten. They are written as a competent engineer would
# write them for each baseline, not weakened to make Amin look good - a
# strawman baseline is worse than no baseline, because it produces a number
# that cannot be defended.

PLAIN_SYSTEM = """You are a helpful assistant. Answer the question concisely.
If you do not know the answer, say so."""


NAIVE_RAG_SYSTEM = """You are a helpful assistant. Use the context passages below
to answer the question. Be concise. If the context does not contain the answer,
say you don't know."""


def format_passages(retrieved: list[Retrieved]) -> tuple[str, dict[str, str]]:
    """Render passages as [S1]..[Sn] and return the tag -> chunk_id mapping."""
    lines, mapping = [], {}
    for i, r in enumerate(retrieved, start=1):
        tag = f"S{i}"
        mapping[tag] = r.chunk_id
        head = f" - {r.chunk.heading}" if r.chunk.heading else ""
        lines.append(f"[{tag}] {r.chunk.doc_id}{head} (tier: {r.chunk.tier.label})\n{r.chunk.text}")
    return "\n\n".join(lines), mapping


def answer_prompt(question: str, retrieved: list[Retrieved]) -> tuple[str, dict[str, str]]:
    passages, mapping = format_passages(retrieved)
    prompt = (
        f"{passages}\n\n"
        f"<question>{question}</question>\n\n"
        "Answer using only the passages above, tagging every sentence."
    )
    return prompt, mapping


def verify_prompt(claim: str, passage: str) -> str:
    return (
        "VERIFY\n"
        f"<passage>{passage}</passage>\n"
        f"<claim>{claim}</claim>\n"
        "Is the claim stated by the passage? Answer YES or NO."
    )


def rewrite_prompt(question: str) -> str:
    return (
        "Rewrite the question below as a keyword search query for a document index. "
        "Keep proper nouns, numbers and domain terms. Drop filler words. "
        "Output only the query, no explanation.\n\n"
        f"<question>{question}</question>"
    )
