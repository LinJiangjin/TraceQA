"""数据库会话与初始化。

启动时自动建表，避免第一天被 Alembic 迁移挡住。
真正上生产时再引入 Alembic 做版本化迁移（见 Milestone M4）。
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Base

settings = get_settings()

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建扩展 + 建表 + 建 pgvector / GIN 索引 + 灌 demo 用户。

    顺序不能换：chunks.embedding 是 vector 类型，扩展没装时 create_all 会直接
    报 `type "vector" does not exist`。pgvector 镜像里扩展是"已安装未启用"，
    所以这一步必须由应用自己补上。

    idx_documents_acl 是 ACL 过滤能不能走索引的关键，
    数据量上万后没它，检索会退化成全表扫描。
    """
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")

    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_documents_acl "
            "ON documents USING gin (acl)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
            "ON chunks USING hnsw (embedding vector_cosine_ops)"
        )

    # users 表是空的，X-User-Id / Bearer 都过不了鉴权，本地起服务后一步都走不动。
    # 生产环境不灌（OIDC 接管后用户来自 IdP）。
    if not settings.is_production:
        from app.seed import seed_demo_users

        with SessionLocal() as db:
            seed_demo_users(db)
