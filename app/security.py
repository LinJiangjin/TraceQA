"""演示级身份认证：本地 HMAC 签发的 JWT + 请求头直指定用户两种方式。

生产要换成真 OIDC（Keycloak / Okta / Entra ID），流程保持一致：
token -> 解出 user_id / tenant_id / roles -> 交给检索层做 ACL 过滤。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from jwt import InvalidTokenError

from app.config import get_settings

settings = get_settings()

BEARER_PREFIX = "bearer "
DEMO_HEADER_SOURCE = "demo-header"


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: list[str]


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """带上凭据来源，便于 /me 回显和排障（例如知道自己在用 demo 通道）。"""

    principal: Principal
    source: Literal["bearer", "demo-header"]

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def tenant_id(self) -> str:
        return self.principal.tenant_id

    @property
    def roles(self) -> list[str]:
        return self.principal.roles


def issue_token(principal: Principal, ttl_seconds: int | None = None) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": principal.user_id,
        "tenant_id": principal.tenant_id,
        "roles": principal.roles,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds or settings.jwt_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:
        raise PermissionError("登录已失效，请重新登录") from exc

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if not user_id or not tenant_id:
        raise PermissionError("凭据缺少必要声明")
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=list(claims.get("roles") or []))


def authenticate_request(
    authorization: str | None,
    x_user_id: str | None,
    *,
    demo_header_enabled: bool | None = None,
) -> AuthenticatedPrincipal:
    """解析请求身份：优先 Bearer token，其次演示用 X-User-Id。

    demo 通道默认只在非 production 环境开启，避免生产环境被绕过鉴权。
    """
    allow_demo = demo_header_enabled
    if allow_demo is None:
        allow_demo = not settings.is_production

    if authorization:
        raw = authorization.strip()
        if raw[: len(BEARER_PREFIX)].lower() != BEARER_PREFIX:
            raise PermissionError("Authorization 格式应为 Bearer <token>")
        token = raw[len(BEARER_PREFIX) :].strip()
        if not token:
            raise PermissionError("Authorization token 为空")
        return AuthenticatedPrincipal(verify_token(token), source="bearer")

    if x_user_id and allow_demo:
        from app.models import User  # 延迟导入，避免循环依赖

        from app.db import SessionLocal

        with SessionLocal() as db:
            user = db.get(User, x_user_id)
            if user is None:
                raise PermissionError("用户不存在")
            return AuthenticatedPrincipal(
                Principal(user_id=user.id, tenant_id=user.tenant_id, roles=list(user.roles)),
                source=DEMO_HEADER_SOURCE,
            )

    raise PermissionError("缺少 Authorization 头或演示用户头")
