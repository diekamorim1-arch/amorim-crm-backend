from datetime import UTC, datetime

from fastapi import BackgroundTasks

from app.core.audit import log_audit_event
from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owner_or_self
from app.modules.attachments.service import BUCKET as ATTACHMENTS_BUCKET


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


def create_contact(
    tenant_id: str, user_id: str, data: dict, background_tasks: BackgroundTasks, is_impersonating: bool = False
) -> dict:
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
    background_tasks.add_task(log_audit_event, tenant_id, user_id, "INSERT", "contacts", contact["id"])
    return contact


def update_contact(
    tenant_id: str, user_id: str, contact_id: str, patch: dict, background_tasks: BackgroundTasks,
    is_impersonating: bool = False,
) -> dict:
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
    background_tasks.add_task(log_audit_event, tenant_id, user_id, "UPDATE", "contacts", contact_id)
    return rows[0]


def get_contact_deletion_summary(tenant_id: str, contact_id: str) -> dict:
    sb = get_service_client()
    if not sb.table("contacts").select("id").eq("tenant_id", tenant_id).eq("id", contact_id).execute().data:
        raise AppError(404, "not_found", "Cliente não encontrado.")
    return {
        "deals": sb.table("deals").select("id", count="exact").eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute().count,
        "appointments": sb.table("appointments").select("id", count="exact").eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute().count,
        "activities": sb.table("activities").select("id", count="exact").eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute().count,
        "attachments": sb.table("attachments").select("id", count="exact").eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute().count,
    }


def delete_contact(tenant_id: str, user_id: str, contact_id: str, background_tasks: BackgroundTasks) -> None:
    sb = get_service_client()
    if not sb.table("contacts").select("id").eq("tenant_id", tenant_id).eq("id", contact_id).execute().data:
        raise AppError(404, "not_found", "Cliente não encontrado.")

    # Diferente de fornecedor/produto: contact_id é NOT NULL em deals,
    # appointments, activities, conversations e attachments — não dá pra só
    # desvincular, excluir um cliente precisa cascatear de verdade tudo que
    # pertence só a ele.
    deal_ids = [
        d["id"]
        for d in sb.table("deals").select("id").eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute().data
    ]
    if deal_ids:
        # Mesma limpeza feita em delete_deal: activities/appointments/attachments
        # referenciam deal_id opcionalmente com FK NO ACTION — sem isso o
        # delete dos negócios abaixo quebraria caso algum desses registros
        # pertença a OUTRO contato mas aponte pra um negócio deste.
        sb.table("activities").update({"deal_id": None}).eq("tenant_id", tenant_id).in_("deal_id", deal_ids).execute()
        sb.table("appointments").update({"deal_id": None}).eq("tenant_id", tenant_id).in_("deal_id", deal_ids).execute()
        sb.table("attachments").update({"deal_id": None}).eq("tenant_id", tenant_id).in_("deal_id", deal_ids).execute()

    conversation_ids = [
        c["id"]
        for c in sb.table("conversations")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("contact_id", contact_id)
        .execute()
        .data
    ]
    if conversation_ids:
        sb.table("messages").delete().eq("tenant_id", tenant_id).in_("conversation_id", conversation_ids).execute()
        sb.table("conversations").delete().eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute()

    attachment_rows = (
        sb.table("attachments")
        .select("id, storage_path")
        .eq("tenant_id", tenant_id)
        .eq("contact_id", contact_id)
        .execute()
        .data
    )
    if attachment_rows:
        sb.storage.from_(ATTACHMENTS_BUCKET).remove([row["storage_path"] for row in attachment_rows])
        sb.table("attachments").delete().eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute()

    sb.table("appointments").delete().eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute()
    sb.table("activities").delete().eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute()
    sb.table("deals").delete().eq("tenant_id", tenant_id).eq("contact_id", contact_id).execute()
    sb.table("contacts").delete().eq("tenant_id", tenant_id).eq("id", contact_id).execute()
    background_tasks.add_task(log_audit_event, tenant_id, user_id, "DELETE", "contacts", contact_id)
