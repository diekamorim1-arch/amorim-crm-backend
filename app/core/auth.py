from dataclasses import dataclass

from app.core.errors import AppError
from app.core.supabase_client import get_service_client


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str | None
    role: str
    email: str
    is_impersonating: bool = False


def extract_claims(payload: dict) -> AuthContext:
    app_metadata = payload.get("app_metadata", {})
    role = app_metadata.get("role")
    if not role:
        raise AppError(401, "invalid_token", "Token sem papel definido.")
    return AuthContext(
        user_id=payload["sub"],
        tenant_id=app_metadata.get("tenant_id"),
        role=role,
        email=payload.get("email", ""),
    )


def decode_token(token: str) -> dict:
    sb = get_service_client()
    try:
        response = sb.auth.get_user(token)
    except Exception as exc:
        raise AppError(401, "invalid_token", "Token inválido ou expirado.") from exc
    if not response or not response.user:
        raise AppError(401, "invalid_token", "Token inválido ou expirado.")
    user = response.user
    return {"sub": user.id, "email": user.email, "app_metadata": user.app_metadata or {}}
