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
    """解析后的统一中间结构，与具体文件格式解耦。

    Attributes:
        title: 展示用标题，会进入 sources[].title。
        content: 纯文本正文，交给 `split_text()` 切段。
        source_uri: 来源路径，用于前端展示与人工核对。
        metadata: 解析器附加信息（类型、页数、needs_ocr 等），写入 documents.doc_metadata。
    """

    title: str
    content: str
    source_uri: str
    metadata: dict


# 三个正则分别负责：去 HTML 标签、压缩水平空白（含全角空格）、收敛连续空行。
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t　]+")
_NL = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    """统一换行、压缩空白、去掉首尾空白，保证切分结果稳定。

    只做无害的格式归一，不做内容改写 —— 引用必须能还原成原文。
    """
    text = text.replace("\r\n", "\n").replace("\u00a0", " ")
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()


def load_markdown(path: Path) -> RawDocument:
    """读取 Markdown：取首个标题行作为标题，正文保留 Markdown 原文。"""
    content = path.read_text(encoding="utf-8", errors="ignore")
    title = content.lstrip("# ").split("\n", 1)[0][:200] or path.stem
    return RawDocument(title=title, content=_clean(content), source_uri=str(path), metadata={"type": "markdown"})


def load_html(path: Path) -> RawDocument:
    """读取 HTML：先去掉 script/style 块，再剥标签并反转义实体。"""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    title_match = re.search(r"(?is)<title>(.*?)</title>", body)
    title = html.unescape(title_match.group(1)).strip() if title_match else path.stem
    text = html.unescape(_TAG.sub("\n", body))
    return RawDocument(title=title, content=_clean(text), source_uri=str(path), metadata={"type": "html"})


def load_pdf(path: Path) -> RawDocument:
    """用 pypdf 逐页抽取文本，并标记疑似扫描件。

    单页文本少于 20 字符视为疑似扫描页；超过半数时打上 `needs_ocr`，
    交由后续 OCR 流程处理，而不是把空内容直接灌进向量库。
    """
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


# 后缀 -> 解析函数映射；未命中的后缀由 load_any() 当纯文本处理。
LOADERS = {".md": load_markdown, ".markdown": load_markdown, ".html": load_html, ".htm": load_html, ".pdf": load_pdf}


def load_any(path: Path) -> RawDocument:
    """按扩展名分派解析器；未知类型（如 .txt）退化为纯文本读取。"""
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        return RawDocument(
            title=path.stem,
            content=_clean(path.read_text(encoding="utf-8", errors="ignore")),
            source_uri=str(path),
            metadata={"type": "text"},
        )
    return loader(path)
