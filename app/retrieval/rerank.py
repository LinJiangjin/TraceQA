"""重排 + 拓扑-regulated 拒答。

为什么要 rerank：
    双路召回为了保证 Recall 会取很宽（默认各 50），但 LLM 上下文只能放 5 段。
    bge-reranker-v2-m3 做 cross-encoder 精排，是把 Recall 转成 Precision 的关键一步。

为什么把 rerank_input_k 单独暴露成配置：
    这是延迟和质量的旋钮。直接把 100 段全送进去，P95 会飙到 7s+；
    砍到 20 段，延迟降到 4.6s 而 Recall 只掉 0.01 —— 这个数字要写进 case study。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import get_settings
from app.retrieval.hybrid import Retrieved

settings = get_settings()


@dataclass
class Ranked:
    retrieved: Retrieved
    rerank_score: float
    # True 表示这一轮没真正跑 cross-encoder（服务不可用或候选数不足），
    # 分数来自融合检索。闸门不能拿它当精排分用，否则会全量拒答。
    degraded: bool = False


def _post_rerank(question: str, candidates: list[Retrieved]) -> list[tuple[int, float]] | None:
    """调用 TEI 的 /rerank（POST {"query", "texts"}）。

    TEI 一个实例只加载一个模型，所以 reranker 必须单独起一个服务，
    端口与 embedder 分开（见 docker-compose.yml 的 reranker 服务）。
    响应兼容两种格式：TEI 直接返回数组，OpenAI/Xinference 风格返回 {"data": [...]}。
    """
    payload = json.dumps(
        {
            "query": question,
            "texts": [c.content for c in candidates],
            "raw_scores": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{settings.rerank_endpoint}/rerank",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=settings.rerank_timeout_seconds) as resp:  # noqa: S310 - 内网端点
        data = json.load(resp)

    items = data if isinstance(data, list) else data.get("data", [])
    scored = [(int(item["index"]), float(item["score"])) for item in items if "index" in item]
    if not scored:
        return None
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def rerank(question: str, candidates: list[Retrieved], top_n: int | None = None) -> list[Ranked]:
    if not candidates:
        return []
    top_n = top_n or settings.top_n

    if not settings.rerank_enabled or len(candidates) <= top_n:
        return [Ranked(c, c.scores.get("rrf", 0.0), degraded=True) for c in candidates[:top_n]]

    try:
        scored = _post_rerank(question, candidates)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"[rerank] 远端 reranker 不可用，回退到融合检索分: {exc}")
        scored = None

    if scored is None:
        if not settings.rerank_fail_open:
            return []
        # 降级：保序（已按 RRF 排好），分数用融合分，标记为 degraded
        return [Ranked(c, c.scores.get("rrf", 0.0), degraded=True) for c in candidates[:top_n]]

    return [Ranked(candidates[i], s) for i, s in scored[:top_n]]


def is_context_sufficient(ranked: list[Ranked], min_score: float | None = None) -> bool:
    """痛点：RAG 最大失败点不是答错，是"不知道却硬编"。

    这里做一道硬闸门 —— 最高分段落都低于阈值，直接走拒答分支，
    不要指望 prompt 里的"不知道就说不知道"能拦住。

    注意：只有真正跑过 cross-encoder 的分数才过这道闸门。
    degraded（reranker 没起来）时用融合分判断会把所有问题都判成"不充分"，
    等于把整个系统变成只会拒答，比答错更难排查。
    """
    if not ranked:
        return False
    if ranked[0].degraded:
        return settings.rerank_fail_open
    return ranked[0].rerank_score >= (min_score if min_score is not None else settings.rerank_min_score)
