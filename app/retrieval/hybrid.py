"""混合检索：BM25(tsvector) + 向量，ACL 前置过滤，RRF 融合。

设计要点（面试常问，务必理解后再改）：

1. 为什么 ACL 必须在 SQL 层过滤，而不是检索完再在 Python 里筛？
   - 若先取 top-k 再过滤，无权限的高相似段落会占据名额，过滤后剩下的可能是垃圾，
     答案质量直接崩塌；
   - 更严重的是"留 embarrassment 泄漏"风险：某些实现会把它留在 LLM 上下文里；
   - 因此 tenant_id + ACL 一律下推到 WHERE，`d.acl && :roles` 走 GIN 索引。

2. 为什么中文用 bigram 而不是装 zhparser？
   - Postgres 原生 FTS 的 simple/zh 配置不支持中文分词；
   - 客户环境（内网、受限镜像）往往装不了第三方扩展；
   - bigram 是"在约束下能落地"的工程取舍，召回够用，代价是索引体积翻倍。
   - 所以 query 侧与入库侧必须用同一个 `to_search_text()`，否则检索失效。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.utils import vec_literal

settings = get_settings()

# 连续汉字作为一个 token（量词 + 不能少，否则只会逐字匹配，bigram 全部失效）
_TOKEN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


def to_search_text(content: str) -> str:
    """入库侧与查询侧共用的文本预处理。

    英文/数字按词切，中文按 bigram 切。例如 "年假怎么请" -> "年假 假怎 怎么 么请"。
    """
    buf: list[str] = []
    for token in _TOKEN.findall(content):
        if re.match(r"^[a-zA-Z0-9_]+$", token):
            buf.append(token.lower())
        else:  # 中文 chunk
            for i in range(len(token) - 1):
                buf.append(token[i : i + 2])
            if len(token) == 1:
                buf.append(token)
    return " ".join(buf)


@dataclass
class Retrieved:
    chunk_id: int
    document_id: int
    content: str
    title: str
    source_uri: str
    scores: dict


# 两路召回各自取 retrieve_k，然后加权融合。
# 注意：ACL 过滤同时出现在两个 CTE 里，任何一路漏了都会造成越权泄漏。
_HYBRID_SQL = text(
    """
WITH visible AS (
    SELECT c.id, c.content, c.document_id, c.tsv, c.embedding,
           d.title, d.source_uri
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.tenant_id = :tenant_id
      -- acl 列是 varchar(64)[]，这里不能 CAST 成 text[]：
      -- varchar[] && text[] 没有对应操作符（operator does not exist）。
      -- 转成 varchar[] 才能走到 idx_documents_acl 这个 GIN 索引。
      AND d.acl && CAST(:roles AS varchar[])
),
lex_raw AS (
    SELECT id, content, document_id, title, source_uri,
           ts_rank_cd(tsv, plainto_tsquery('simple', :q)) AS sc
    FROM visible
    WHERE tsv @@ plainto_tsquery('simple', :q)
    ORDER BY sc DESC
    LIMIT :k
),
lex AS (
    SELECT *, ROW_NUMBER() OVER (ORDER BY sc DESC) AS rk FROM lex_raw
),
sem_raw AS (
    -- 注意：这里不能再 JOIN chunks。visible 已经含 chunks 的列，
    -- 再 join 一次会让 `id` 变成 ambiguous column reference。
    SELECT id, content, document_id, title, source_uri,
           1 - (embedding <=> CAST(:vec AS vector)) AS sc
    FROM visible
    ORDER BY embedding <=> CAST(:vec AS vector)
    LIMIT :k
),
sem AS (
    SELECT id, content, document_id, title, source_uri, sc,
           ROW_NUMBER() OVER (ORDER BY sc DESC) AS rk
    FROM sem_raw
),
pooled AS (
    SELECT id, content, document_id, title, source_uri, sc, rk, 'lexical'  AS src FROM lex
    UNION ALL
    SELECT id, content, document_id, title, source_uri, sc, rk, 'semantic' AS src FROM sem
)
SELECT id, content, document_id, title, source_uri,
       SUM(1.0 / (:rrf_k + rk))                                        AS rrf,
       COALESCE(MAX(sc) FILTER (WHERE src = 'lexical'),  0.0)          AS bm25,
       COALESCE(MAX(sc) FILTER (WHERE src = 'semantic'), 0.0)          AS cosine
FROM pooled
GROUP BY id, content, document_id, title, source_uri
ORDER BY rrf DESC
LIMIT :limit_n
"""
)


def hybrid_retrieve(
    db: Session,
    *,
    tenant_id: str,
    roles: list[str],
    question: str,
    query_vector: list[float],
    k: int | None = None,
    limit_n: int | None = None,
) -> list[Retrieved]:
    """返回按 RRF 融合排序的候选段落。ACL 已在此处完成过滤。"""
    rows = db.execute(
        _HYBRID_SQL,
        {
            "tenant_id": tenant_id,
            "roles": roles,
            "q": to_search_text(question),
            # 必须转成 pgvector 字面量字符串：text() 里的参数不走 Vector 的
            # bind_processor，直接传 list 会被 psycopg 转成 PG 数组 {..}，CAST 到 vector 会失败。
            "vec": vec_literal(query_vector),
            "k": k or settings.retrieve_k,
            "rrf_k": settings.rrf_k,
            "limit_n": limit_n or settings.rerank_input_k,
        },
    ).fetchall()

    return [
        Retrieved(
            chunk_id=r.id,
            document_id=r.document_id,
            content=r.content,
            title=r.title,
            source_uri=r.source_uri,
            scores={"rrf": float(r.rrf), "bm25": float(r.bm25), "cosine": float(r.cosine)},
        )
        for r in rows
    ]
