from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant


def list_activities(tenant_id: str, contact_id: str) -> list[dict]:
    sb = get_service_client()
    return (
        sb.table("activities")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def list_recent_activities(tenant_id: str, limit: int) -> list[dict]:
    sb = get_service_client()
    return (
        sb.table("activities")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def create_activity(tenant_id: str, user_id: str, data: dict) -> dict:
    sb = get_service_client()
    # Mesma vulnerabilidade recorrente das Tasks 6/7/8/9: contact_id e deal_id vêm
    # direto do body do cliente. Sem estas checagens, um usuário do tenant A
    # poderia criar uma atividade apontando para um contato ou negócio de outro
    # tenant (tenant_id da atividade fica correto, mas os ids referenciados
    # vazariam dados entre tenants).
    verify_owned_by_tenant("contacts", data["contact_id"], tenant_id, "Cliente não encontrado.")
    if data.get("deal_id") is not None:
        verify_owned_by_tenant("deals", data["deal_id"], tenant_id, "Negócio não encontrado.")
    return sb.table("activities").insert({**data, "tenant_id": tenant_id, "user_id": user_id}).execute().data[0]
