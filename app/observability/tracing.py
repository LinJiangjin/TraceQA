"""OpenTelemetry 初始化。

为什么一开始就埋：FDE 交付后要回答"为什么慢""为什么贵""为什么答错了"，
没有 trace 就只能靠猜。上线后再补埋点的成本是现在的十倍。

当前状态：只完成 Provider 初始化，`get_tracer()` 尚未在问答链路中创建 span，
也就是说「框架已接线、埋点待补」。要观测 P95 / 各阶段耗时，
需要在 `run_qa()` 的嵌入、检索、精排、生成各阶段分别开 span。
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.config import get_settings

settings = get_settings()


def setup_tracing() -> None:
    """注册全局 TracerProvider，并按配置选择导出方式。

    优先级：配置了 `otel_endpoint` -> OTLP HTTP 上报；
    否则 debug 模式 -> 控制台打印；两者都没有时只建立 Provider、不导出。
    使用 BatchSpanProcessor 批量上报，避免同步阻塞请求。
    """
    provider = TracerProvider(resource=Resource.create({"service.name": settings.app_name}))

    if settings.otel_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint)))
    elif settings.debug:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


def get_tracer(name: str = "tracingqa"):
    """获取 tracer；`setup_tracing()` 必须在进程启动时先调用。

    Args:
        name: instrumentation scope 名称，用于在后端区分不同模块的 span。
    """
    return trace.get_tracer(name)
