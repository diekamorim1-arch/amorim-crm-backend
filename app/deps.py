from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, Header

from app.core.auth import AuthContext, decode_token, extract_claims
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


async def get_current_user(
    authorization: str = Header(default=""),
    x_impersonate_tenant: str | None = Header(default=None),
) -> AuthContext:
    if not authorization.startswith("Bearer "):
        raise AppError(401, "missing_token", "Cabeçalho Authorization ausente ou inválido.")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    context = extract_claims(payload)

    # admin_saas "entrando como gestor" numa loja: o frontend envia esse
    # header em toda requisição enquanto a impersonação está ativa. Só
    # admin_saas pode disparar isso — um gestor/atendente enviando o header
    # não tem nenhum efeito, o contexto real deles é usado normalmente.
    if x_impersonate_tenant and context.role == "admin_saas":
        return AuthContext(
            user_id=context.user_id,
            tenant_id=x_impersonate_tenant,
            role="gestor",
            email=context.email,
        )

    return context


def require_role(*roles: str) -> Callable[..., AuthContext]:
    def checker(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role not in roles:
            raise AppError(403, "forbidden", f"Papel '{user.role}' não tem acesso a este recurso.")
        return user

    return checker


def _check_billing(tenant_id: str) -> None:
    sb = get_service_client()
    rows = sb.table("tenants").select("billing_status, plan_expires_at").eq("id", tenant_id).execute().data
    if not rows:
        return
    billing_status = rows[0]["billing_status"]
    expires_at = rows[0]["plan_expires_at"]
    if billing_status == "em_dia" or not expires_at:
        return
    if datetime.fromisoformat(expires_at) < datetime.now(UTC):
        raise AppError(403, "plan_expired", "O plano desta loja está vencido — renove para continuar.")


def require_tenant(user: AuthContext = Depends(get_current_user)) -> str:
    if not user.tenant_id:
        raise AppError(400, "no_tenant", "Esta ação exige um tenant ativo na sessão.")
    _check_billing(user.tenant_id)
    return user.tenant_id
