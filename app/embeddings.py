"""轻量 --fallback 检索 + 排序，模型/ with-openai 输出 Session = None。"""
from __future__ import annotations

import json
import math
import urllib.request
import uuid
from collections import Counter

from app.config import get_settings

settings = get_settings()


def _tokenize(text: str) -> list[str]:
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
    """哈希向量作为 demo fallback。

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
        items = sorted(data.get("data", []), key=lambda x: x["index"])
        if len(items) != len(texts):
            return None
        return [item["embedding"] for item in items]
    except Exception as exc:
        print(f"[embeddings] 远端嵌入不可用，回退到本地哈希向量: {exc}")
        return None


def _hash_vector(text: str, dim: int) -> list[float]:
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
    return uuid.uuid4().hex
