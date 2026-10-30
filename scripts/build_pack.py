"""Build knowledge packs (Task 3, amin/packs.py) from openly licensed sources.

    uv run python scripts/build_pack.py python-docs   # docs.python.org text archive (PSF-2.0)
    uv run python scripts/build_pack.py openstax <repo> <slug> "<title>"   # OpenStax (CC BY 4.0)
    uv run python scripts/build_pack.py warm <slug>...   # embed once, so switching a pack on is instant

Every pack carries its licence and attribution in pack.json, and the
attribution is repeated at the top of each document, so a cited passage is
never separated from its source. Raw downloads stay under data/packs/raw
(gitignored with the rest of data/packs).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("data/packs")
RAW = ROOT / "raw"


def write_pack(name: str, meta: dict, docs: dict[str, str]) -> None:
    out = ROOT / name / "docs"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    for fname, text in docs.items():
        (out / fname).write_text(text, encoding="utf-8")
    (ROOT / name / "pack.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{name}: {len(docs)} documents, {sum(len(t) for t in docs.values()) / 1e6:.1f} MB → {ROOT / name}")


# -- Python documentation -------------------------------------------------------

KEEP = ("tutorial", "library", "reference", "howto", "faq", "using")
TOP = ("glossary.txt",)
# reST section underlines, in the order Python's docs nest them.
LEVELS = {"*": 1, "=": 2, "-": 3, "~": 4, "^": 4, '"': 4}


def rst_to_md(text: str) -> str:
    """Turn reST underline headings into Markdown ones; leave the prose as it is."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if (line.strip() and nxt and len(set(nxt.strip())) == 1 and nxt.strip()[0] in LEVELS
                and len(nxt.strip()) >= max(3, len(line.strip()) - 2)):
            out.append("#" * LEVELS[nxt.strip()[0]] + " " + line.strip())
            i += 2
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def python_docs() -> None:
    base = next((RAW / "pydocs").glob("python-*-docs-text"))
    version = base.name.split("-")[1]
    attribution = f"Python {version} documentation, © Python Software Foundation, PSF License Agreement."
    docs = {}
    files = [p for d in KEEP for p in sorted((base / d).rglob("*.txt"))] + [base / t for t in TOP]
    for p in files:
        rel = p.relative_to(base).with_suffix("")
        md = rst_to_md(p.read_text(encoding="utf-8", errors="replace"))
        if len(md.strip()) < 200:
            continue
        docs["py-" + "-".join(rel.parts) + ".md"] = (
            f"---\ntitle: Python docs · {'/'.join(rel.parts)}\ntier: reference\nlang: en\n"
            f"about: python-docs\nnote: {attribution}\n---\n\n{md}\n")
    write_pack("python-docs", {
        "title": f"Python {version} documentation",
        "description": "The official Python tutorial, library reference, language reference, how-tos and FAQ.",
        "licence": "PSF License Agreement (PSF-2.0)",
        "attribution": attribution,
        "source": "https://docs.python.org/3/download.html",
    }, docs)


# -- OpenStax ------------------------------------------------------------------------

NS = {"c": "http://cnx.rice.edu/cnxml", "md": "http://cnx.rice.edu/mdml"}


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def cnxml_to_md(path: Path) -> tuple[str, str]:
    root = ET.parse(path).getroot()
    title = root.findtext("c:title", default="", namespaces=NS) or path.parent.name
    out = []

    def walk(el, depth: int) -> None:
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag == "section":
                t = child.find("c:title", NS)
                if t is not None:
                    out.append("#" * min(depth, 4) + " " + _text(t))
                walk(child, depth + 1)
            elif tag in ("para", "note", "example", "exercise", "list", "table", "equation", "definition"):
                text = _text(child)
                if text:
                    out.append(text)
            elif tag == "content":
                walk(child, depth)

    content = root.find("c:content", NS)
    if content is not None:
        walk(content, 2)
    return title, f"# {title}\n\n" + "\n\n".join(out)


def openstax(repo: str, slug: str, title: str) -> None:
    dest = RAW / repo
    if not dest.exists():
        # Text only: a sparse, blobless clone skips the media folders entirely.
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse",
                        f"https://github.com/openstax/{repo}.git", str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", "modules", "collections"], check=True)
    attribution = (f"{title} by OpenStax, licensed under CC BY 4.0 "
                   f"(https://creativecommons.org/licenses/by/4.0/). Source: https://openstax.org.")
    docs = {}
    for cnxml in sorted((dest / "modules").glob("*/index.cnxml")):
        try:
            mtitle, md = cnxml_to_md(cnxml)
        except ET.ParseError:
            continue
        if len(md) < 400:
            continue
        # Readable file names become readable citations ("dna-replication.md").
        fname = re.sub(r"[^a-z0-9]+", "-", mtitle.lower()).strip("-")[:60] or cnxml.parent.name
        if f"{fname}.md" in docs:
            fname += "-" + cnxml.parent.name
        docs[f"{fname}.md"] = (
            f"---\ntitle: {title} · {mtitle}\ntier: reference\nlang: en\nabout: {slug}\n"
            f"note: {attribution}\n---\n\n{md}\n")
    write_pack(slug, {
        "title": title, "description": f"{title}, an open textbook by OpenStax (Rice University).",
        "licence": "CC BY 4.0", "attribution": attribution, "source": f"https://github.com/openstax/{repo}",
    }, docs)


# -- warm the embedding cache --------------------------------------------------------


def warm(*names: str) -> None:
    """Embed every passage of each pack into the shared vector cache (amin/vcache.py)."""
    import time

    from amin.api import _parse
    from amin.providers import OllamaProvider

    embedder = OllamaProvider()
    for name in names:
        start, n = time.time(), 0
        for path in sorted((ROOT / name / "docs").glob("*.md")):
            _, chunks = _parse(path, f"k.{name}.{path.name}")
            if chunks:
                embedder.embed([c.text for c in chunks])
                n += len(chunks)
        print(f"{name}: {n} passages embedded or already cached in {time.time() - start:.0f}s")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"python-docs": python_docs, "openstax": openstax, "warm": warm}[cmd](*args)
