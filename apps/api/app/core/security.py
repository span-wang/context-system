from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import HTTPException, status


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    parts = password_hash.split("$")
    if len(parts) != 4 or parts[0] != PASSWORD_SCHEME:
        return _verify_legacy_seed_password(password, password_hash)
    _, iterations, salt, expected = parts
    try:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(subject: str, secret_key: str, expires_seconds: int) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_seconds,
        "typ": "access",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64_url(signature)}"


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str, secret_key: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
    except ValueError as exc:
        raise _auth_error("无效登录令牌") from exc

    signing_input = f"{header_raw}.{payload_raw}"
    expected_signature = hmac.new(secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64_url(expected_signature), signature_raw):
        raise _auth_error("登录令牌签名无效")

    payload = _json_from_b64(payload_raw)
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        raise _auth_error("登录已过期")
    return payload


def _verify_legacy_seed_password(password: str, password_hash: str) -> bool:
    legacy_map = {
        "seed-admin-password": {"admin", "admin123456"},
        "seed-learner-password": {"learner", "learner123456"},
    }
    return password in legacy_map.get(password_hash, set())


def _auth_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _b64_json(data: dict[str, Any]) -> str:
    return _b64_url(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _json_from_b64(value: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(_with_padding(value))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise _auth_error("登录令牌内容无效") from exc
    if not isinstance(payload, dict):
        raise _auth_error("登录令牌内容无效")
    return payload


def _b64_url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _with_padding(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return f"{value}{padding}".encode("ascii")
