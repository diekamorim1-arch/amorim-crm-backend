from datetime import UTC, datetime

from app.core.audit import log_audit_event
from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owner_or_self


def list_contacts(
    tenant_id: str,
    journey_status: str | None,
    tag: str | None,
    origin: str | None,
    owner_id: str | None,
    search: str | None,
) -> list[dict]:
    sb = get_service_client()
    query = sb.table("contacts").select("*").eq("tenant_id", tenant_id)
    if journey_status:
        query = query.eq("journey_status", journey_status)
    if origin:
        query = query.eq("origin", origin)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if tag:
        query = query.contains("tags", [tag])
    if search:
        query = query.or_(f"name.ilike.%{search}%,whatsapp.ilike.%{search}%")
    return query.execute().data


def get_contact(tenant_id: str, contact_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("contacts").select("*").eq("tenant_id", tenant_id).eq("id", contact_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Cliente não encontrado.")
    return rows[0]


def create_contact(tenant_id: str, user_id: str, data: dict, is_impersonating: bool = False) -> dict:
    sb = get_service_client()
    owner_id = data.get("owner_id")
    if owner_id is not None:
        verify_owner_or_self(owner_id, tenant_id, user_id, is_impersonating, "Responsável não encontrado.")
    now = datetime.now(UTC).isoformat()
    payload = {
        **data,
        "tenant_id": tenant_id,
        "journey_status": "lead",
        "first_contact_at": now,
        "last_interaction_at": now,
    }
    contact = sb.table("contacts").insert(payload).execute().data[0]
    log_audit_event(tenant_id, user_id, "INSERT", "contacts", contact["id"])
    return contact


def update_contact(tenant_id: str, user_id: str, contact_id: str, patch: dict, is_impersonating: bool = False) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    if "owner_id" in clean_patch:
        verify_owner_or_self(clean_patch["owner_id"], tenant_id, user_id, is_impersonating, "Responsável não encontrado.")
    rows = (
        sb.table("contacts")
        .update(clean_patch)
        .eq("tenant_id", tenant_id)
        .eq("id", contact_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Cliente não encontrado.")
    log_audit_event(tenant_id, user_id, "UPDATE", "contacts", contact_id)
    return rows[0]
