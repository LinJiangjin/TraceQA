from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全部配置环境变量化。私有化交付时客户只需要改 .env，不用碰代码。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- 服务 ----
    app_name: str = "TraceQA"
    debug: bool = False
    environment: str = "dev"          # dev | staging | production

    @property
    def is_production(self) -> bool:
        """生产环境会关闭演示用的 X-User-Id 通道，避免绕过鉴权。"""
        return self.environment.lower() == "production"

    # ---- 演示数据 ----
    demo_tenant_id: str = "acme"

    # ---- 数据库 ----
    database_url: str = "postgresql+psycopg://tracingqa:tracingqa@localhost:5432/tracingqa"

    # ---- 嵌入（本地部署，客户环境可能禁止出网）----
    embedding_provider: str = "local"          # local | openai
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_endpoint: str = "http://localhost:9997"   # Xinference / TEI
    embedding_timeout_seconds: int = 10

    # ---- 重排 ----
    # reranker 是独立服务（一个 TEI 实例只能加载一个模型），端口与 embedder 分开。
    rerank_enabled: bool = True
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_endpoint: str = "http://localhost:9998"
    rerank_timeout_seconds: int = 30
    # 上下文充分性闸门阈值。调低 -> 更容易硬答（幻觉变多）；调高 -> 更容易拒答。
    # 这是 evals 里第二个要扫的参数，不要凭感觉定。
    rerank_min_score: float = 0.35
    # reranker 没起来时是否放行。True: 用融合检索分兜底，不因一个组件挂掉就全量拒答。
    rerank_fail_open: bool = True

    # ---- LLM（litellm 统一，可在 Claude / OpenAI / DeepSeek / vLLM 间切换）----
    llm_provider: str = "deepseek"             # deepseek | openai | anthropic | ollama
    llm_model: str = "deepseek-chat"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float = 0.0

    # ---- 检索 ----
    retrieve_k: int = 50          # 每路召回数量
    rerank_input_k: int = 20      # 送进 rerank 的数量（控制延迟的关键旋钮）
    top_n: int = 5                # 最终进 LLM 上下文的段落数
    rrf_k: int = 60

    # ---- 安全 ----
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 3600 * 12

    # ---- 观测 ----
    otel_endpoint: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
