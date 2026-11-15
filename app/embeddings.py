"""文本嵌入：优先调用本地/远端嵌入服务，不可用时回退到哈希向量。

回退设计的目的是让 demo 在完全离线的客户环境里也能跑通，
但哈希向量只反映词面重合、没有语义能力，不能用于评估检索质量。
"""

from __future__ import annotations

import json
import math
import urllib.request
import uuid
from collections import Counter

from app.config import get_settings

settings = get_settings()


def _tokenize(text: str) -> list[str]:
    """极简分词：英文/数字按空白与标点切，中文额外产出相邻二元组（bigram）。

    与 `app.retrieval.hybrid.to_search_text()` 思路一致，
    目的是让没有中文分词器的 Postgres 环境也能做词面匹配。
    """
    tokens = []
    for token in text.replace("\n", " ").split():
        token = token.strip().strip(",.;:!?()[]{}<>\"'").lower()
        if token:
            tokens.append(token)
    # 中文按 bigram 切，与 lexical 保持一致
    compact = text.replace(" ", "").replace("\n", "")
    for i in range(len(compact) - 1):
        tokens.append(compact[i : i + 2])
    return tokens


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量，返回顺序与入参一一对应。

    哈希向量作为 demo fallback。

    生产请切换到 bge-m3（本地 Xinference / TEI 或 OpenAI 兼容接口）。
    切换方式：把 settings.embedding_provider 设成 "local" 或 "openai"，
    其余调用方无需改动 —— 这是为了让同一个 demo 在离线客户环境也能跑通。
    """
    if settings.embedding_provider in ("local", "openai"):
        vectors = _try_remote_embeddings(texts)
        if vectors is not None:
            return vectors

    return [_hash_vector(t, settings.embedding_dim) for t in texts]


def _try_remote_embeddings(texts: list[str]) -> list[list[float]] | None:
    """请求 OpenAI 兼容的 /v1/embeddings 接口。

    Returns:
        成功返回按 index 排序后的向量列表；请求失败、返回条数不符时返回 None，
        由调用方决定降级，避免单个外部组件故障导致整个问答不可用。
    """
    try:
        payload = json.dumps(
            {"model": settings.embedding_model, "input": texts}, ensure_ascii=False
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{settings.embedding_endpoint}/v1/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=settings.embedding_timeout_seconds) as resp:
            data = json.load(resp)
        # 服务可能乱序返回，必须按 index 重排，否则向量与文本会错位。
        items = sorted(data.get("data", []), key=lambda x: x["index"])
        if len(items) != len(texts):
            return None
        return [item["embedding"] for item in items]
    except Exception as exc:
        print(f"[embeddings] 远端嵌入不可用，回退到本地哈希向量: {exc}")
        return None


def _hash_vector(text: str, dim: int) -> list[float]:
    """基于词频的哈希向量（bag-of-words + L2 归一化）。

    用 token 的 hash 落到固定维度；注意 Python 的 hash 有进程随机化，
    重启后同一文本可能得到不同向量，因此只适合「同一次进程内」的演示。
    """
    vec = [0.0] * dim
    counts = Counter(_tokenize(text))
    for token, weight in counts.items():
        idx = hash(token) % dim
        vec[idx] += float(weight)
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def chunk_id() -> str:
    """生成段落主键，等价于 new_id()，保留给灌库脚本显式调用。"""
    return uuid.uuid4().hex
