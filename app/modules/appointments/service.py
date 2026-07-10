from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant


def list_appointments(tenant_id: str, date_from: str | None, date_to: str | None, contact_id: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("appointments").select("*").eq("tenant_id", tenant_id)
    if date_from:
        query = query.gte("starts_at", date_from)
    if date_to:
        query = query.lte("starts_at", date_to)
    if contact_id:
        query = query.eq("contact_id", contact_id)
    return query.order("starts_at").execute().data


def create_appointment(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    # Mesma vulnerabilidade recorrente das Tasks 6/7/8: contact_id, deal_id e
    # owner_id vêm direto do body do cliente. Sem estas checagens, um usuário
    # do tenant A poderia criar um agendamento apontando para um contato,
    # negócio ou responsável de outro tenant (tenant_id do agendamento fica
    # correto, mas os ids referenciados vazariam dados entre tenants).
    verify_owned_by_tenant("contacts", data["contact_id"], tenant_id, "Cliente não encontrado.")
    if data.get("deal_id") is not None:
        verify_owned_by_tenant("deals", data["deal_id"], tenant_id, "Negócio não encontrado.")
    verify_owned_by_tenant("user_profiles", data["owner_id"], tenant_id, "Responsável não encontrado.")
    return sb.table("appointments").insert({**data, "tenant_id": tenant_id}).execute().data[0]


def update_appointment(tenant_id: str, appointment_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    # contact_id/deal_id/owner_id agora são editáveis (antes só starts_at/ends_at/
    # status/note) — mesma checagem de tenant já aplicada em create_appointment,
    # senão um usuário do tenant A poderia revincular o agendamento a um
    # contato/negócio/responsável de outro tenant.
    if "contact_id" in clean_patch:
        verify_owned_by_tenant("contacts", clean_patch["contact_id"], tenant_id, "Cliente não encontrado.")
    if "deal_id" in clean_patch:
        verify_owned_by_tenant("deals", clean_patch["deal_id"], tenant_id, "Negócio não encontrado.")
    if "owner_id" in clean_patch:
        verify_owned_by_tenant("user_profiles", clean_patch["owner_id"], tenant_id, "Responsável não encontrado.")
    rows = (
        sb.table("appointments")
        .update(clean_patch)
        .eq("tenant_id", tenant_id)
        .eq("id", appointment_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Agendamento não encontrado.")
    return rows[0]
