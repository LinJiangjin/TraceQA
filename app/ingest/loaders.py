"""文档解析。真实客户环境里这一步占的工作量常常超过一半。

先做到能处理：PDF（含扫描件的 OCR 兜底）、HTML、Markdown、Word。
脏数据不要在这里洗白 —— 保留原文 anomalies，用 metadata 标记，
因为 evals 里"脏数据"本身就是你要证明能处理的东西。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawDocument:
    title: str
    content: str
    source_uri: str
    metadata: dict


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t　]+")
_NL = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\u00a0", " ")
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()


def load_markdown(path: Path) -> RawDocument:
    content = path.read_text(encoding="utf-8", errors="ignore")
    title = content.lstrip("# ").split("\n", 1)[0][:200] or path.stem
    return RawDocument(title=title, content=_clean(content), source_uri=str(path), metadata={"type": "markdown"})


def load_html(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    title_match = re.search(r"(?is)<title>(.*?)</title>", body)
    title = html.unescape(title_match.group(1)).strip() if title_match else path.stem
    text = html.unescape(_TAG.sub("\n", body))
    return RawDocument(title=title, content=_clean(text), source_uri=str(path), metadata={"type": "html"})


def load_pdf(path: Path) -> RawDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError("处理 PDF 需要 pypdf：uv add pypdf") from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    scanned = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if len(text.strip()) < 20:
            scanned += 1  # 疑似扫描件，交给 OCR 兜底
        pages.append(text)

    content = _clean("\n\n".join(pages))
    metadata = {"type": "pdf", "pages": len(reader.pages), "suspected_scanned_pages": scanned}
    if scanned > len(reader.pages) * 0.5:
        metadata["needs_ocr"] = True

    return RawDocument(title=path.stem, content=content, source_uri=str(path), metadata=metadata)


LOADERS = {".md": load_markdown, ".markdown": load_markdown, ".html": load_html, ".htm": load_html, ".pdf": load_pdf}


def load_any(path: Path) -> RawDocument:
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        return RawDocument(
            title=path.stem,
            content=_clean(path.read_text(encoding="utf-8", errors="ignore")),
            source_uri=str(path),
            metadata={"type": "text"},
        )
    return loader(path)
