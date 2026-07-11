from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def verify_owned_by_tenant(table: str, row_id: str, tenant_id: str, not_found_message: str) -> None:
    sb = get_service_client()
    rows = sb.table(table).select("id").eq("tenant_id", tenant_id).eq("id", row_id).execute().data
    if not rows:
        raise AppError(404, "not_found", not_found_message)


def verify_owner_or_self(
    owner_id: str, tenant_id: str, caller_user_id: str, is_impersonating: bool, not_found_message: str
) -> None:
    # user_profiles não tem uma linha pro admin_saas neste tenant (o perfil
    # dele tem tenant_id null) — verify_owned_by_tenant sempre rejeitaria o
    # admin como responsável, mesmo estando impersonando a loja via "Entrar
    # como gestor". Quando quem está sendo escolhido como responsável é o
    # próprio chamador impersonando, aceita sem a checagem de vínculo — pra
    # qualquer outro owner_id (inclusive um user_id arbitrário tentando se
    # passar pelo admin), a checagem normal continua valendo.
    if is_impersonating and owner_id == caller_user_id:
        return
    verify_owned_by_tenant("user_profiles", owner_id, tenant_id, not_found_message)
