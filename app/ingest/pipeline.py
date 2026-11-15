"""ingestion 管线：解析 → 切分 → 嵌入 → 入库。

切分策略是 evals 里第一个要优化的变量。默认 256/64 是经过大量实践验证的起点，
但不要盲信 —— 用 evals/harness.py 跑出你自己的数据上的最优值，再把结论写进 case study。

用法：
    python -m app.ingest.pipeline --input sample_docs/employee --tenant acme --acl employee
    python -m app.ingest.pipeline --input sample_docs/hr --tenant acme --acl employee,hr
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.embeddings import embed_texts
from app.ingest.loaders import load_any
from app.retrieval.hybrid import to_search_text
from app.utils import new_id, vec_literal

SUPPORTED = {".md", ".markdown", ".html", ".htm", ".pdf", ".txt"}

# 切分时优先在段落/句子边界断开，避免把一句话切成两半导致引用不可用
_SENT_SPLIT = "。！？；\n"


def split_text(content: str, size: int = 256, overlap: int = 64) -> list[str]:
    """按字符窗口切分，尽量在句末标点断开，并在相邻块间保留重叠。

    Args:
        content: 已清洗的正文。
        size: 每块最大字符数。
        overlap: 相邻块重叠字符数，降低边界信息丢失。

    Returns:
        非空段落列表；正文为空时返回 []。

    注意：只有断点落在窗口后半段（> size*0.5）才采用，
    否则切出的块会过短，导致向量与索引里充斥碎片。
    """
    if len(content) <= size:
        return [content] if content.strip() else []

    chunks: list[str] = []
    start = 0
    n = len(content)

    while start < n:
        end = min(start + size, n)
        if end < n:
            # 向前找最近的句末标点作为断点
            boundary = max((content.rfind(p, start + 1, end) for p in _SENT_SPLIT), default=-1)
            if boundary > start + size * 0.5:
                end = boundary + 1
        piece = content[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, 0)

    return chunks


def ingest_file(
    path: Path,
    *,
    tenant_id: str,
    acl: list[str],
    size: int = 256,
    overlap: int = 64,
) -> int:
    """灌入单个文件：解析、切分、批量嵌入，然后写 documents + chunks 两张表。

    Args:
        tenant_id: 文档所属租户。
        acl: 允许访问的角色标签列表，作为文档级权限写入 documents.acl。
        size / overlap: 透传给 `split_text()`。

    Returns:
        写入的段落数；文件无可索引内容时返回 0。
    """
    doc = load_any(path)
    chunks = split_text(doc.content, size=size, overlap=overlap)
    if not chunks:
        print(f"[skip] {path.name}：无可索引内容")
        return 0

    # 一次请求算完所有段落的向量，避免逐段调用模型服务带来的高延迟。
    vectors = embed_texts(chunks)
    document_id = new_id()

    with SessionLocal() as db:
        # 注意：`:metadata::jsonb` 这种写法会被 SQLAlchemy 的 text() 误当成
        # "参数 :metadata 后面跟字面量 :jsonb"，最后拼出非法的 `:metadata::jsonb`，
        # 报 syntax error at or near ":"。必须用 CAST(... AS jsonb)。
        db.execute(
            text(
                "INSERT INTO documents (id, tenant_id, source_uri, title, acl, doc_metadata) "
                "VALUES (:id, :tenant_id, :source_uri, :title, :acl, CAST(:metadata AS jsonb))"
            ),
            {
                "id": document_id,
                "tenant_id": tenant_id,
                "source_uri": doc.source_uri,
                "title": doc.title,
                "acl": acl,
                "metadata": __import__("json").dumps(doc.metadata, ensure_ascii=False),
            },
        )

        # search_text 必须与查询侧共用 to_search_text()，否则 BM25 一路召回失效；
        # embedding 先转成 pgvector 字面量，SQL 里再 CAST 成 vector 类型。
        rows = [
            {
                "id": new_id(),
                "document_id": document_id,
                "content": c,
                "chunk_index": i,
                "token_count": len(c),
                "embedding": vec_literal(v),
                "search_text": to_search_text(c),
            }
            for i, (c, v) in enumerate(zip(chunks, vectors, strict=False))
        ]
        # executemany：一次提交所有段落，比逐条 INSERT 快一个量级。
        db.execute(
            text(
                "INSERT INTO chunks (id, document_id, content, chunk_index, token_count, embedding, search_text) "
                "VALUES (:id, :document_id, :content, :chunk_index, :token_count, "
                "CAST(:embedding AS vector), :search_text)"
            ),
            rows,  # type: ignore[arg-type]
        )
        db.commit()

    print(f"[ok] {path.name} -> {len(chunks)} chunks (acl={acl})")
    return len(chunks)


def main() -> None:
    """CLI 入口：递归扫描目录，把支持的文档逐个灌入同一个 tenant/ACL 下。

    --acl 用逗号分隔多个角色；不同权限的文档要分多次执行，
    例如 sample_docs/hr 单独用 `--acl employee,hr` 灌入。
    """
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="文档目录")
    p.add_argument("--tenant", default="acme")
    p.add_argument("--acl", default="employee", help="逗号分隔的角色，例如 employee,hr")
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--overlap", type=int, default=64)
    args = p.parse_args()

    root = Path(args.input)
    files = [f for f in root.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED]
    if not files:
        print(f"目录里没找到支持的文档：{root}")
        return

    acl = [a.strip() for a in args.acl.split(",") if a.strip()]
    total = sum(ingest_file(f, tenant_id=args.tenant, acl=acl, size=args.size, overlap=args.overlap) for f in files)
    print(f"完成：{len(files)} 份文档 / {total} 个段落")


if __name__ == "__main__":
    main()
