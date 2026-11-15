"""ORM 数据模型：用户、文档、段落、问答审计、评测留档共 5 张表。

关系：Document 1 --- N Chunk（外键级联删除），QALog / EvalRun 为独立事实表。
当前没有 Alembic 版本化迁移，表结构由 `app.db.init_db()` 在启动时 `create_all` 创建，
因此字段变更需要手动同步既有数据库。
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    ARRAY,
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import declarative_base

from app.config import get_settings

settings = get_settings()
Base = declarative_base()


class User(Base):
    """用户/身份主体。tenant_id 与 roles 共同决定检索时可见的文档范围。"""

    __tablename__ = "users"

    id = Column(String(32), primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    tenant_id = Column(String(64), nullable=False, index=True)
    roles = Column(ARRAY(String(64)), nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """一份原始文档的记录；权限标签挂在文档级，其下所有 chunk 继承同一 ACL。"""

    __tablename__ = "documents"

    id = Column(String(32), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    source_uri = Column(String(1024), nullable=False)
    title = Column(String(512), nullable=False)
    # 文档级 ACL。存角色标签，检索时用 d.acl && :roles 做数组交集判断。
    acl = Column(ARRAY(String(64)), nullable=False, default=[])
    # 解析器产出的附加信息（页数、疑似扫描页数、needs_ocr 等），不参与检索。
    doc_metadata = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    """切分后的段落，是检索、引用与溯源的最小单位。"""

    __tablename__ = "chunks"

    id = Column(String(32), primary_key=True)
    document_id = Column(String(32), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, default=0)
    # 维度必须与嵌入模型一致（bge-m3 = 1024），改模型要同步改 embedding_dim 并重建列。
    embedding = Column(Vector(settings.embedding_dim))
    # 预处理后的检索文本（中文 bigram + 英文词），查询侧必须用同一套 to_search_text()
    search_text = Column(String, nullable=False)
    # 数据库生成列：由 search_text 自动填充 tsvector，供 BM25 侧排名使用。
    # 放在 DB 里做而不是应用层做，是为了保证 query/update 永远一致。
    tsv = Column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# 复合索引配合检索 SQL 的 tenant_id = ... AND acl && ... 过滤条件。
Index("ix_documents_tenant_acl", Document.tenant_id, Document.acl)


class QALog(Base):
    """审计表。留证据：任何一次问答都要能复盘到它依据了哪几段。"""

    __tablename__ = "qa_logs"

    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), index=True)
    tenant_id = Column(String(64), index=True)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    citations = Column(JSON, default=[])
    refused = Column(Boolean, default=False)
    # 记录的是「召回候选」而非「最终引用」，便于事后分析漏召回问题。
    retrieved_chunk_ids = Column(ARRAY(String(32)), default=[])
    latency_ms = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class EvalRun(Base):
    """每次评测留档，用于生成 case study 里的指标爬坡表。

    表已定义，但 `evals/harness.py` 目前只打印报告，尚未写入此表。
    """

    __tablename__ = "eval_runs"

    id = Column(String(32), primary_key=True)
    git_commit = Column(String(16))
    variant = Column(String(64), index=True)
    metrics = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
