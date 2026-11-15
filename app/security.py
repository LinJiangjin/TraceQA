"""演示级身份认证：本地 HMAC 签发的 JWT + 请求头直指定用户两种方式。

生产要换成真 OIDC（Keycloak / Okta / Entra ID），流程保持一致：
token -> 解出 user_id / tenant_id / roles -> 交给检索层做 ACL 过滤。

本模块只负责「谁在请求」，不负责「能看到什么」：后者由检索层的
 tenant_id + ACL 条件决定，是真正的安全边界。
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
    """鉴权后的最小身份信息，会作为 JWT claims 或传给检索层。

    frozen=True 防止链路中途被意外篡改角色，导致权限提升。
    """

    user_id: str
    tenant_id: str
    roles: list[str]


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """带上凭据来源，便于 /me 回显和排障（例如知道自己在用 demo 通道）。

    下面三个 property 只是转发，让调用方不必层层取 `.principal`。
    """

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
    """用本地 HMAC 密钥签发 JWT。

    Args:
        principal: 写入 sub / tenant_id / roles 的身份信息。
        ttl_seconds: 覆盖默认有效期（settings.jwt_ttl_seconds）。

    Returns:
        编码后的 JWT 字符串；生产应改为由 IdP 签发与校验。
    """
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
    """校验签名与有效期，并把 claims 还原成 Principal。

    Raises:
        PermissionError: 签名错误/过期，或缺少 sub、tenant_id 等必要声明。
    """
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

    Args:
        authorization: Authorization 头原文，格式 `Bearer <token>`。
        x_user_id: 演示用户 ID，仅在各环境明确允许时生效。
        demo_header_enabled: 显式覆盖开关，主要给单测使用；None 表示按环境判断。

    Raises:
        PermissionError: 头格式错误、token 无效、用户不存在或没有任何身份凭据。
    """
    allow_demo = demo_header_enabled
    if allow_demo is None:
        allow_demo = not settings.is_production

    # 分支一：标准 Bearer 通道，身份信息全部来自已签名的 token。
    if authorization:
        raw = authorization.strip()
        if raw[: len(BEARER_PREFIX)].lower() != BEARER_PREFIX:
            raise PermissionError("Authorization 格式应为 Bearer <token>")
        token = raw[len(BEARER_PREFIX) :].strip()
        if not token:
            raise PermissionError("Authorization token 为空")
        return AuthenticatedPrincipal(verify_token(token), source="bearer")

    # 分支二：演示通道。角色不从请求头读取，而是查库取真实用户记录，
    # 避免调用方自己拼一个 roles 数组来提权。
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
