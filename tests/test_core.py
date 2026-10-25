"""只测纯函数部分 —— 不依赖数据库，CI 里能快速跑。

数据库相关的行为用 evals/harness.py 做端到端验证，不放单元测试。
"""

from app.ingest.pipeline import split_text
from app.retrieval.hybrid import to_search_text


def test_to_search_text_splits_chinese_into_bigrams():
    out = to_search_text("年假怎么申请")
    # 中文按 bigram：年假 / 假怎 / 怎么 / 么申 / 申请
    assert "年假" in out
    assert "怎么" in out
    assert "申请" in out
    assert "年 假" not in out  # 不能被拆成单字


def test_to_search_text_lowercases_english():
    out = to_search_text("OAuth 2.0 Token")
    assert "oauth" in out
    assert "token" in out


def test_split_text_respects_size_and_overlap():
    content = "第一句话在这里。" * 200
    chunks = split_text(content, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 130 for c in chunks)


def test_split_text_prefers_sentence_boundary():
    content = "这是第一句话。" + "啊" * 200 + "这是第二句话。"
    chunks = split_text(content, size=80, overlap=10)
    # 不应把同一句话切得零碎到难以引用
    assert chunks
    assert "这是第一句话。" in chunks[0]
