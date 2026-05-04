"""JWT bearer auth for the control plane.

Single-secret model: per-deployment shared secret in env var
`LIPMM_CONTROL_SECRET`. The frontend exchanges the secret for a JWT
(24h expiry by default) and includes the JWT as `Authorization: Bearer
<jwt>` on every subsequent request.

Why single-secret instead of multi-user accounts:
  - Each operator runs their own bot deployment (per the trading club setup).
  - One operator per bot → no need for per-user permissions.
  - Sharing across club members happens via shared deployment, not shared
    user accounts.
  - Scaling to multi-user (per-user accounts, RBAC) is future work outside
    this PR.

Security notes:
  - HS256 (symmetric). The secret signs and verifies — same key.
  - Short (24h) token expiry. Refresh by re-authenticating.
  - The secret MUST be set via env var; the server fails loudly at startup
    if it isn't.
  - JWT 'sub' claim records the actor name (default: "operator"); shows
    up in audit records so you can scope expansion later without changing
    the audit schema.
"""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

logger = logging.getLogger(__name__)


SECRET_ENV_VAR = "LIPMM_CONTROL_SECRET"
JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_TTL_S = 24 * 3600  # 24 hours
DEFAULT_ACTOR = "operator"


class AuthMisconfigured(RuntimeError):
    """Raised at server startup if LIPMM_CONTROL_SECRET isn't set or is
    obviously weak (empty, < 16 chars). Fail-loud so operators don't
    accidentally run an unauthenticated control plane."""


def get_secret() -> str:
    """Read the shared secret from env. Validates length to discourage
    "test"/"changeme"-style values landing in production."""
    secret = os.environ.get(SECRET_ENV_VAR, "").strip()
    if not secret:
        raise AuthMisconfigured(
            f"{SECRET_ENV_VAR} env var is required. "
            f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(secret) < 16:
        raise AuthMisconfigured(
            f"{SECRET_ENV_VAR} must be at least 16 chars; "
            f"got {len(secret)}. Use a generated value, not a phrase."
        )
    return secret


def issue_token(
    secret: str | None = None,
    *,
    actor: str = DEFAULT_ACTOR,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_S,
) -> str:
    """Mint a fresh JWT. Caller is expected to have already verified the
    operator presented the correct shared secret. Secret reads from env
    if not passed (production path)."""
    secret = secret if secret is not None else get_secret()
    now = int(time.time())
    payload = {
        "sub": actor,
        "iat": now,
        "exp": now + ttl_seconds,
        # jti = JWT ID; rotates per token, useful for logging which token
        # made which request without leaking the whole JWT.
        "jti": _secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_token(token: str, secret: str | None = None) -> dict:
    """Verify a JWT and return its claims. Raises HTTPException on
    failure (so it composes with FastAPI's auth dependency machinery)."""
    secret = secret if secret is not None else get_secret()
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def constant_time_secret_compare(provided: str, expected: str) -> bool:
    """Constant-time string compare; resists timing attacks on the secret
    exchange endpoint."""
    return _secrets.compare_digest(provided.encode(), expected.encode())


# FastAPI dependency: validates the Authorization header on protected routes.
# Use as: `actor: str = Depends(require_auth)` in route handlers.
_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ] = None,
) -> str:
    """Returns the actor (sub claim) on success, raises 401 otherwise.

    Uses request.app.state.control_secret if set (test injection),
    otherwise the env-var secret. This indirection lets test fixtures
    swap the secret per-test without touching the env."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization: Bearer <token> required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    secret = getattr(request.app.state, "control_secret", None) or get_secret()
    claims = verify_token(credentials.credentials, secret=secret)
    actor = claims.get("sub", DEFAULT_ACTOR)
    return actor
