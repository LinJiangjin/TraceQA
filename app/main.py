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
    init_db()          # 建表 + 灌 demo 数据
    setup_tracing()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


def _resolve_principal(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    db=Depends(get_db),
) -> AuthenticatedPrincipal:
    """演示用的身份解析。

    优先接受 Bearer token；没有 token 时允许用 X-User-Id 指定 demo 用户，
    方便 curl 直接验证权限隔离。生产实现请换成真正的 OIDC 校验（见 auth.py）。
    """
    try:
        principal = authenticate_request(authorization, x_user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if principal.source != "demo-header" and not db.get(User, principal.user_id):
        raise HTTPException(status_code=401, detail="登录用户不存在，请重新登录")

    return principal


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/v1/me")
def me(principal: AuthenticatedPrincipal = Depends(_resolve_principal), db=Depends(get_db)):
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
    """演示用登录：查询已有用户并直接签发 token。"""
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "access_token": issue_token(Principal(user_id=user.id, tenant_id=user.tenant_id, roles=user.roles)),
        "token_type": "bearer",
    }


@app.get("/api/v1/admin/qa-logs")
def list_qa_logs(db=Depends(get_db), limit: int = 20):
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
