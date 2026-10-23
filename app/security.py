"""Small HS256 JWT implementation and FastAPI RBAC dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


@dataclass(frozen=True, slots=True)
class AuthUser:
    username: str
    role: str


def create_access_token(settings: Settings, username: str, role: str = "admin") -> tuple[str, int]:
    now = int(time.time())
    expires_in = settings.jwt_expire_minutes * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
        "iss": "zhiku",
    }
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}", expires_in


def decode_access_token(settings: Settings, token: str) -> AuthUser:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        supplied = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid signature")
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
        if header.get("alg") != "HS256" or payload.get("iss") != "zhiku":
            raise ValueError("invalid token metadata")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("token expired")
        username = str(payload.get("sub", "")).strip()
        role = str(payload.get("role", "")).strip()
        if not username or role not in {"viewer", "admin"}:
            raise ValueError("invalid claims")
        return AuthUser(username=username, role=role)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def verify_admin_credentials(settings: Settings, username: str, password: str) -> bool:
    return secrets.compare_digest(username, settings.admin_username) and secrets.compare_digest(
        password, settings.admin_password
    )


def build_current_user_dependency(settings: Settings) -> Callable:
    bearer = HTTPBearer(auto_error=False)

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> AuthUser:
        if not settings.auth_enabled:
            return AuthUser(username="local-user", role="admin")
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少Bearer访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return decode_access_token(settings, credentials.credentials)

    return get_current_user


def require_roles(current_user_dependency: Callable, *allowed_roles: str) -> Callable:
    async def dependency(user: AuthUser = Depends(current_user_dependency)) -> AuthUser:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权执行此操作")
        return user

    return dependency
