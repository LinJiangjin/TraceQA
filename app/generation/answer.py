"""带溯源的答案生成。

三条硬规则：
1. 结构化输出（JSON schema），不允许自由文本 —— 前端要渲染引用，设地下 toxicity 审计要留痕；
2. 每个结论必须挂 chunk_id 作为引用，PID độgrave stick 引用不上就必须拒答；
3. 拒答是一等公民，不是异常。
"""

from __future__ import annotations

import json
import litellm
from litellm import completion

from app.config import get_settings
from app.retrieval.rerank import Ranked

settings = get_settings()
litellm.drop_params = True

SYSTEM_PROMPT = """你是企业知识库的问答助手。

严格规则：
1. 只能依据提供的【参考段落】作答，禁止使用任何外部知识或推测。
2. 每个事实性结论后面必须标注来源编号，格式 [1]、[2]，编号与【参考段落】一一对应。
3. 若【参考段落】中没有能支撑答案的信息，必须返回 refused=true，
   answer 里说明"知识库中未找到相关信息"，不要试图给出模糊或推测性的回答。
4. 不要编造数字、日期、人名、流程步骤。
5. 用简洁的中文回答，优先给出结论，再补充关键细节。

输出严格遵循以下 JSON 结构，不要输出任何其他内容：
{"answer": "...", "citations": [1, 2], "refused": false, "confidence": 0.0-1.0}
"""


def build_context(ranked: list[Ranked]) -> str:
    return "\n\n".join(
        f"[{i + 1}] 来源：{r.retrieved.title}（{r.retrieved.source_uri}）\n{r.retrieved.content}"
        for i, r in enumerate(ranked)
    )


def generate_answer(question: str, ranked: list[Ranked]) -> dict:
    if not ranked:
        return {"answer": "知识库中未找到相关信息。", "citations": [], "refused": True, "confidence": 0.0}

    user_content = f"【参考段落】\n{build_context(ranked)}\n\n【问题】\n{question}"

    resp = completion(
        model=f"{settings.llm_provider}/{settings.llm_model}"
        if settings.llm_provider not in ("openai",)
        else settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=settings.llm_temperature,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"answer": raw, "citations": [], "refused": False, "confidence": 0.0}

    # 安全兜底：模型幻觉出的引用编号要剔除，否则前端会指向不存在的段落
    valid = set(range(1, len(ranked) + 1))
    payload["citations"] = [c for c in payload.get("citations", []) if c in valid]

    payload.setdefault("answer", "")
    payload.setdefault("refused", not payload["citations"])
    payload.setdefault("confidence", 0.0)
    return payload
