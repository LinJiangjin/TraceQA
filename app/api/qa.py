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
    """POST /api/v1/qa 的请求体。

    Attributes:
        question: 用户问题。
        top_n: 可选，覆盖最终进 LLM 上下文的段落数，供评测扫参数用。

    注意：这里刻意不含 tenant_id / roles，身份只由服务端解析，防止客户端伪造。
    """

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
    """执行一次完整问答：嵌入 → 混合检索 → 精排 → 充分性闸门 → 生成/拒答 → 审计。

    Args:
        db: SQLAlchemy 会话，用于检索、读写审计日志。
        tenant_id: 租户 ID，参与检索层的第一道隔离。
        roles: 用户角色标签列表，与文档的 acl 数组做交集匹配。
        question: 用户问题原文。
        user_id: 提问者 ID，写入审计表；评测调用时可为 None。
        embed_text: 单条文本的嵌入函数（接收 str，返回 list[float]）。
            以参数注入是为了让 evals 能替换实现，也避免本模块依赖具体模型服务。
        top_n: 覆盖 settings.top_n，用于评测时做参数扫点。

    Returns:
        字典，字段与 `web/src/types.ts` 的 QAResponse 一一对应：
        question / answer / citations / cited_chunk_ids / refused /
        confidence / sources / latency_ms。

    Side Effects:
        无论回答还是拒答，都会向 qa_logs 写入一条记录并提交事务。
    """
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
        # 引用编号是 1-based，映射回 ranked 里对应的 chunk_id 供前端定位原文。
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
