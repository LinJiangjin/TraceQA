"""TraceQA 的 HTTP 入口（薄控制器层）。

职责：
1. 应用生命周期：启动时建表/建索引/灌 demo 用户，并初始化 OpenTelemetry；
2. 身份解析：把 Bearer token 或演示用 X-User-Id 解析成 Principal；
3. 暴露 5 个接口：健康检查、当前身份、问答、演示登录、审计日志。

这里刻意不写检索/生成逻辑，全部委托给 `app.api.qa.run_qa()`，
保证 HTTP 请求与 `evals/harness.py` 评测走的是同一条问答链路。
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Header

from app.api.qa import QARequest, run_qa
from app.config import get_settings
from app.db import get_db, init_db
from app.embeddings import embed_texts
from app.models import User
from app.observability.tracing import setup_tracing
from app.security import AuthenticatedPrincipal, Principal, authenticate_request, issue_token

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动阶段：先初始化库表与索引，再初始化可观测性；关闭时无需额外清理。"""
    init_db()          # 建表 + 灌 demo 数据
    setup_tracing()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


def _resolve_principal(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db=Depends(get_db),
) -> AuthenticatedPrincipal:
    """把请求头解析为已认证身份，供各路由通过 `Depends` 注入。

    优先接受 Bearer token；没有 token 时允许用 X-User-Id 指定 demo 用户，
    方便 curl 直接验证权限隔离。生产实现请换成真正的 OIDC 校验（见 auth.py）。

    Raises:
        HTTPException: 401 —— 凭据格式错误/失效、用户不存在或缺少身份头。
    """
    try:
        principal = authenticate_request(authorization, x_user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    # Bearer 通道还要确认用户确实在库里（demo 通道已在 security 层查过一次）。
    if principal.source != "demo-header" and not db.get(User, principal.user_id):
        raise HTTPException(status_code=401, detail="登录用户不存在，请重新登录")

    return principal


@app.get("/healthz")
def healthz():
    """健康检查：供 Docker HEALTHCHECK 与 compose 的 depends_on 使用。"""
    return {"status": "ok"}


@app.get("/api/v1/me")
def me(principal: AuthenticatedPrincipal = Depends(_resolve_principal), db=Depends(get_db)):
    """回显当前身份（租户、角色、凭据来源），前端据此展示「我是谁、能看到什么」。"""
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": user.tenant_id,
        "roles": user.roles,
        "auth_source": principal.source,
    }


@app.post("/api/v1/qa")
def qa(
    payload: QARequest,
    principal: AuthenticatedPrincipal = Depends(_resolve_principal),
    db=Depends(get_db),
):
    """问答主接口。

    身份不信任请求体：tenant_id / roles 一律从数据库里的用户记录取，
    避免调用方伪造角色越权；嵌入函数在这里注入，方便评测替换为桩实现。
    """
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")

    return run_qa(
        db,
        tenant_id=user.tenant_id,
        roles=user.roles,
        question=payload.question,
        user_id=user.id,
        embed_text=lambda text: embed_texts([text])[0],
        top_n=payload.top_n,
    )


@app.post("/api/v1/admin/login")
def admin_login(email: str, db=Depends(get_db)):
    """演示用登录：查询已有用户并直接签发 token。

    注意：这里没有密码/验证码校验，仅用于本地演示；
    生产环境必须替换成 OIDC 或真正的账号密码流程（见 README 的占位实现清单）。
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "access_token": issue_token(Principal(user_id=user.id, tenant_id=user.tenant_id, roles=user.roles)),
        "token_type": "bearer",
    }


@app.get("/api/v1/admin/qa-logs")
def list_qa_logs(db=Depends(get_db), limit: int = 20):
    """按时间倒序列出问答审计记录，供前端 AuditLog 展示。

    Args:
        limit: 返回条数上限，默认 20；前端默认请求 8 条。
    """
    from app.models import QALog

    rows = db.query(QALog).order_by(QALog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "tenant_id": r.tenant_id,
            "question": r.question,
            "answer": r.answer,
            "refused": r.refused,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
