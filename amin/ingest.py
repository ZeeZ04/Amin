"""Corpus ingestion: load -> chunk -> index.

Chunking is structure-aware rather than fixed-window, because the citation UI
is only as good as the chunk boundaries. A chunk that straddles two clauses of
a contract produces a citation that points at the wrong clause, which is worse
than no citation at all.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import settings
from .schema import Chunk, Document, Tier

# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

TEXT_SUFFIXES = {".md", ".txt", ".markdown"}
HTML_SUFFIXES = {".html", ".htm"}


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in HTML_SUFFIXES:
        raw = path.read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", raw)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError("PDF support needs the 'pdf' extra: uv sync --extra pdf") from exc
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    raise ValueError(f"unsupported file type: {path.suffix}")


# ---------------------------------------------------------------------------
# front matter / provenance
# ---------------------------------------------------------------------------

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass
class Parsed:
    meta: dict
    body: str


def split_front_matter(raw: str) -> Parsed:
    m = FRONT_MATTER.match(raw)
    if not m:
        return Parsed({}, raw)
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return Parsed(meta if isinstance(meta, dict) else {}, raw[m.end() :])


def make_document(path: Path, root: Path) -> tuple[Document, str]:
    parsed = split_front_matter(load_text(path))
    doc_id = parsed.meta.get("id") or path.stem
    tier_raw = str(parsed.meta.get("tier", "unverified")).lower()
    tier = {
        "primary": Tier.PRIMARY,
        "reference": Tier.REFERENCE,
        "secondary": Tier.SECONDARY,
        "unverified": Tier.UNVERIFIED,
    }.get(tier_raw, Tier.UNVERIFIED)
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    doc = Document(
        doc_id=doc_id,
        title=parsed.meta.get("title") or path.stem.replace("-", " ").title(),
        path=rel,
        tier=tier,
        lang=parsed.meta.get("lang", "en"),
        meta={k: v for k, v in parsed.meta.items() if k not in {"id", "title", "tier", "lang"}},
    )
    return doc, parsed.body


# ---------------------------------------------------------------------------
# chunking
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$|^([A-Z0-9][^\n]{0,70})\n[=-]{3,}$", re.M)
_SENT_SPLIT = re.compile(r"(?<=[.!?؟۔])\s+")


def _sections(body: str) -> list[tuple[str, str]]:
    """Split on markdown headings, keeping the heading with its content."""
    matches = list(re.finditer(r"^#{1,6}\s+(.+)$", body, re.M))
    if not matches:
        return [("", body.strip())]
    out: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        if preamble := body[: matches[0].start()].strip():
            out.append(("", preamble))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[m.end() : end].strip()
        if content:
            out.append((m.group(1).strip(), content))
    return out


def _pack(text: str, limit: int, overlap: int) -> list[str]:
    """Pack sentences up to `limit` chars, never splitting mid-sentence."""
    units: list[str] = []
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        # Keep list items and table rows whole: they are often the fact itself.
        if re.match(r"^\s*([-*+]|\d+[.)]|\|)", para):
            units.append(para)
        else:
            units.extend(s.strip() for s in _SENT_SPLIT.split(para) if s.strip())

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for unit in units:
        if size + len(unit) > limit and buf:
            chunks.append(" ".join(buf).strip())
            tail, tail_len = [], 0
            for prev in reversed(buf):
                if tail_len + len(prev) > overlap:
                    break
                tail.insert(0, prev)
                tail_len += len(prev)
            buf, size = tail, tail_len
        buf.append(unit)
        size += len(unit) + 1
    if buf:
        chunks.append(" ".join(buf).strip())
    return [c for c in chunks if c]


def chunk_document(doc: Document, body: str) -> list[Chunk]:
    out: list[Chunk] = []
    ordinal = 0
    for heading, content in _sections(body):
        for piece in _pack(content, settings.chunk_chars, settings.chunk_overlap):
            digest = hashlib.blake2b(
                f"{doc.doc_id}|{ordinal}|{piece}".encode(), digest_size=5
            ).hexdigest()
            out.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}#{ordinal:03d}-{digest}",
                    doc_id=doc.doc_id,
                    ordinal=ordinal,
                    text=piece,
                    heading=heading,
                    tier=doc.tier,
                )
            )
            ordinal += 1
    return out


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

SUPPORTED = TEXT_SUFFIXES | HTML_SUFFIXES | {".pdf"}


def discover(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith(".")
    )


def ingest(root: Path) -> tuple[list[Document], list[Chunk]]:
    docs, chunks = [], []
    for path in discover(root):
        doc, body = make_document(path, root)
        doc_chunks = chunk_document(doc, body)
        if not doc_chunks:
            continue
        docs.append(doc)
        chunks.extend(doc_chunks)
    return docs, chunks
