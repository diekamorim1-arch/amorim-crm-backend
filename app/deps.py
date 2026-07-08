from collections.abc import Callable

from fastapi import Depends, Header

from app.core.auth import AuthContext, decode_token, extract_claims
from app.core.errors import AppError


async def get_current_user(
    authorization: str = Header(default=""),
    x_impersonate_tenant: str | None = Header(default=None),
) -> AuthContext:
    if not authorization.startswith("Bearer "):
        raise AppError(401, "missing_token", "Cabeçalho Authorization ausente ou inválido.")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    context = extract_claims(payload)
    # Impersonação (Task 4): admin_saas manda o header X-Impersonate-Tenant numa
    # requisição normal, autenticada com o PRÓPRIO JWT — nada de mintar token
    # novo. "Voltar ao painel" é só parar de mandar o header, sem estado nenhum
    # pra invalidar.
    if x_impersonate_tenant and context.role == "admin_saas":
        return AuthContext(
            user_id=context.user_id, tenant_id=x_impersonate_tenant, role="gestor", email=context.email
        )
    return context


def require_role(*roles: str) -> Callable[..., AuthContext]:
    def checker(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role not in roles:
            raise AppError(403, "forbidden", f"Papel '{user.role}' não tem acesso a este recurso.")
        return user

    return checker


def require_tenant(user: AuthContext = Depends(get_current_user)) -> str:
    if not user.tenant_id:
        raise AppError(400, "no_tenant", "Esta ação exige um tenant ativo na sessão.")
    return user.tenant_id
