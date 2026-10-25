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
    __tablename__ = "users"

    id = Column(String(32), primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    tenant_id = Column(String(64), nullable=False, index=True)
    roles = Column(ARRAY(String(64)), nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(32), primary_key=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    source_uri = Column(String(1024), nullable=False)
    title = Column(String(512), nullable=False)
    # 文档级 ACL。存角色标签，检索时用 d.acl && :roles 做数组交集判断。
    acl = Column(ARRAY(String(64)), nullable=False, default=[])
    doc_metadata = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(32), primary_key=True)
    document_id = Column(String(32), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, default=0)
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
    retrieved_chunk_ids = Column(ARRAY(String(32)), default=[])
    latency_ms = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class EvalRun(Base):
    """每次评测留档，用于生成 case study 里的指标爬坡表。"""

    __tablename__ = "eval_runs"

    id = Column(String(32), primary_key=True)
    git_commit = Column(String(16))
    variant = Column(String(64), index=True)
    metrics = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
