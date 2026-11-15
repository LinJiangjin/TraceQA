"""通用小工具：ID 生成与 pgvector 字面量转换。"""

import uuid


def new_id() -> str:
    """生成 32 位十六进制主键（去掉连字符的 UUID4）。"""
    return uuid.uuid4().hex


def vec_literal(vec: list[float]) -> str:
    """把 list[float] 转成 pgvector 的字面量字符串，如 "[0.1,0.2]"。

    凡是走 SQLAlchemy text() 的原生 SQL，参数都不会经过 Vector 类型的
    bind_processor：直接传 Python list 会被 psycopg 当成 PG 数组（{0.1,0.2}），
    vector 列不认，报 malformed vector literal / syntax error。
    所以入库和查询两侧都必须先转成这个字符串形式，再 CAST(... AS vector)。

    保留 7 位小数：精度足够余弦相似度使用，同时避免 SQL 过长。
    """
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
