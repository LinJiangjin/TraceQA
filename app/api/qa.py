"""问答主链路。被 API 与评测脚本共同调用 —— 保证"评测的就是线上跑的"。

这一条很重要：很多人的 eval 是抄一份逻辑另写一套，结果评测分数和线上表现对不上。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.generation.answer import generate_answer
from app.models import QALog
from app.retrieval.hybrid import hybrid_retrieve
from app.retrieval.rerank import is_context_sufficient, rerank

settings = get_settings()


@dataclass
class QARequest:
    question: str
    top_n: int | None = None


def run_qa(
    db: Session,
    *,
    tenant_id: str,
    roles: list[str],
    question: str,
    user_id: str | None = None,
    embed_text=None,
    top_n: int | None = None,
) -> dict:
    started = time.perf_counter()

    # ① 嵌入查询
    query_vector = embed_text(question)

    # ② 混合检索（ACL 已在此层过滤，这是安全边界）
    candidates = hybrid_retrieve(
        db, tenant_id=tenant_id, roles=roles, question=question, query_vector=query_vector
    )

    # ③ 精排（top_n 可由调用方覆盖，方便在 evals 里做参数扫点）
    ranked = rerank(question, candidates, top_n=top_n or settings.top_n)

    # ④ 上下文充分性闸门 —— 不够就拒答，不给 LLM 编造的机会
    if not is_context_sufficient(ranked):
        payload = {
            "answer": "知识库中未找到能够回答该问题的相关信息，建议联系对应业务负责人。",
            "citations": [],
            "refused": True,
            "confidence": 0.0,
        }
        cited_chunk_ids: list[str] = []
    else:
        payload = generate_answer(question, ranked)
        cited_chunk_ids = [ranked[i - 1].retrieved.chunk_id for i in payload.get("citations", [])]

    latency_ms = int((time.perf_counter() - started) * 1000)

    # ⑤ 全量审计：任何一次问答都可追溯到"谁问了什么、依据哪几段、答了什么"
    db.add(
        QALog(
            id=uuid.uuid4().hex,
            user_id=user_id,
            tenant_id=tenant_id,
            question=question,
            answer=payload.get("answer", ""),
            citations=[{"index": i, "chunk_id": cid} for i, cid in enumerate(cited_chunk_ids)],
            refused=bool(payload.get("refused")),
            retrieved_chunk_ids=[c.chunk_id for c in candidates],
            latency_ms=latency_ms,
        )
    )
    db.commit()

    return {
        "question": question,
        "answer": payload.get("answer", ""),
        "citations": payload.get("citations", []),
        "cited_chunk_ids": cited_chunk_ids,
        "refused": bool(payload.get("refused")),
        "confidence": payload.get("confidence", 0.0),
        "sources": [
            {
                "index": i + 1,
                "chunk_id": r.retrieved.chunk_id,
                "title": r.retrieved.title,
                "source_uri": r.retrieved.source_uri,
                "content": r.retrieved.content,
                "rerank_score": r.rerank_score,
            }
            for i, r in enumerate(ranked)
        ],
        "latency_ms": latency_ms,
    }
