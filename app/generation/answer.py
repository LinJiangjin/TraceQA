"""带溯源的答案生成。

三条硬规则：
1. 结构化输出（JSON schema），不允许自由文本 —— 前端要渲染引用，审计也要留痕；
2. 每个结论必须挂引用编号 [n]，编号对应不上参考段落就必须拒答；
3. 拒答是一等公民，不是异常。
"""

from __future__ import annotations

import json
import litellm
from litellm import completion

from app.config import get_settings
from app.retrieval.rerank import Ranked

settings = get_settings()
# 不同模型对参数支持不一（例如某些本地模型不认 response_format），
# 交给 litellm 自动丢弃不支持的参数，避免切换 provider 就报错。
litellm.drop_params = True

# 提示词里的编号与 build_context() 生成的 [1]、[2] 严格对应，
# 这是「答案 -> 段落 -> 原文」溯源链的第一环。
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
    """把精排段落拼成带编号的参考材料。

    编号从 1 开始，与返回给前端的 `sources[].index` 保持一致，
    因此引用上标点击后能定位到同一个段落。
    """
    return "\n\n".join(
        f"[{i + 1}] 来源：{r.retrieved.title}（{r.retrieved.source_uri}）\n{r.retrieved.content}"
        for i, r in enumerate(ranked)
    )


def generate_answer(question: str, ranked: list[Ranked]) -> dict:
    """调用 LLM 生成带引用的答案，返回统一结构的字典。

    Args:
        question: 用户问题。
        ranked: 通过充分性闸门后的精排段落。

    Returns:
        {"answer": str, "citations": list[int], "refused": bool, "confidence": float}。
        没有候选、模型返回非法 JSON、或模型没给出有效引用时，都会走/等价于拒答语义。
    """
    if not ranked:
        return {"answer": "知识库中未找到相关信息。", "citations": [], "refused": True, "confidence": 0.0}

    user_content = f"【参考段落】\n{build_context(ranked)}\n\n【问题】\n{question}"

    resp = completion(
        # litellm 用 "provider/model" 定位模型；openai 前缀例外，直接用模型名。
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
        # 模型没按 JSON 返回：保留原文但清空引用，避免前端渲染出无来源的"结论"。
        payload = {"answer": raw, "citations": [], "refused": False, "confidence": 0.0}

    # 安全兜底：模型幻觉出的引用编号要剔除，否则前端会指向不存在的段落
    valid = set(range(1, len(ranked) + 1))
    payload["citations"] = [c for c in payload.get("citations", []) if c in valid]

    payload.setdefault("answer", "")
    # 没有任何有效引用就视为拒答，与上游闸门的语义对齐。
    payload.setdefault("refused", not payload["citations"])
    payload.setdefault("confidence", 0.0)
    return payload
