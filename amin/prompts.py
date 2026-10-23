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


GENERAL_SYSTEM = """You are Amin, a careful, helpful assistant. Your name means trustworthy.

Answer from your own general knowledge, accurately and concisely.
- If you are not sure, say so plainly. Never invent a figure, date or name.
- You cannot see the user's personal documents in this answer. If the question
  is about their own details - their contract, bill, account, appliance,
  school, car or family - say you don't have that information and that adding
  the document to a project would let you answer from it. Do not guess.
- If the question names a specific product, model, plan, company, course or
  person that you do not reliably know, say you don't know it. Never describe
  its features, prices, terms or warranty from what similar things usually
  have.
- Do not use source tags like [S1]; nothing here comes from a document.
- Answer in the same language the question was asked in."""


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


def general_prompt(question: str, searched: bool = False) -> str:
    """`searched`: the user's documents were searched and do not cover this."""
    if not searched:
        return question.strip()
    return (
        "The user's documents were searched and do not answer this question. "
        "If it asks about their own document, plan, product or account, say their "
        "documents don't cover it and stop. Otherwise answer from general knowledge.\n\n"
        f"{question.strip()}"
    )


CONDENSE_SYSTEM = """You turn a follow-up message into a standalone question. You never answer it.
Replace words like it, that, there and the same with what they refer to in the
conversation. Keep the user's language. Output only the question."""


def condense_prompt(history: list[tuple[str, str]], question: str) -> str:
    """`history`: the last few (question, answer) pairs, oldest first."""
    turns = "\n".join(f"User: {q.strip()}\nAmin: {' '.join(a.split())[:300]}" for q, a in history)
    return (
        f"<conversation>\n{turns}\n</conversation>\n\n"
        f"<follow_up>{question.strip()}</follow_up>\n\n"
        "Do not answer it. Rewrite the follow-up as one standalone question, "
        "in the same language, and output only that question."
    )


def rewrite_prompt(question: str) -> str:
    return (
        "Rewrite the question below as a keyword search query for a document index. "
        "Keep proper nouns, numbers and domain terms. Drop filler words. "
        "Output only the query, no explanation.\n\n"
        f"<question>{question}</question>"
    )


# -- abstention detection, shared by every system ------------------------

REFUSAL_MARKERS = (
    "no_evidence",
    "i don't know",
    "i do not know",
    "i don't have",
    "i do not have",
    "cannot answer",
    "can't answer",
    "not able to answer",
    "no information",
    "not mentioned",
    "not specified",
    "not provided",
    "not provide",
    "not specify",
    "not contain",
    "doesn't say",
    "does not say",
    "unable to determine",
    "لا أعرف",
    "لا توجد معلومات",
    "غير مذكور",
    # E27: declines the general fallback produces, missed until then.
    "don't have access",
    "do not have access",
    "documents don't cover",
    "documents do not cover",
    "لا أملك معلومات",
    "لا يمكنني معرفة",
    "لا أستطيع الاطلاع",
    "لا تتوفر لدي",
    "لا تغطي مستنداتك",
)


def looks_like_refusal(text: str) -> bool:
    """Did the model verbally abstain?

    Crediting a baseline with a refusal it did not make would flatter it; missing
    one it did make would flatter Amin. Both are the same error, so this list is
    applied identically to every system, including Amin's own draft stage.
    """
    # Curly apostrophes ("don’t") read as their ASCII form: a model's
    # typography must not decide whether it refused.
    low = text.lower().strip().replace("\u2019", "'").replace("\u2018", "'")
    if not low:
        return False
    return any(marker in low for marker in REFUSAL_MARKERS)
