from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant


def list_conversations(tenant_id: str, assignee_id: str | None, status: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("conversations").select("*").eq("tenant_id", tenant_id)
    if assignee_id == "null":
        query = query.is_("assignee_id", "null")
    elif assignee_id:
        query = query.eq("assignee_id", assignee_id)
    if status:
        query = query.eq("status", status)
    return query.execute().data


def create_conversation(tenant_id: str, contact_id: str) -> dict:
    sb = get_service_client()
    # Vulnerabilidade recorrente (Task 6: deals -> contacts/users; Task 7: suppliers
    # -> suppliers): contact_id vem direto do body do cliente. Sem esta checagem,
    # um usuário do tenant A poderia criar uma conversa apontando para um contato
    # de outro tenant (tenant_id fica correto, mas contact_id vaza dados entre
    # tenants). Precisa validar que o contato pertence ao tenant antes de inserir.
    verify_owned_by_tenant("contacts", contact_id, tenant_id, "Cliente não encontrado.")
    return sb.table("conversations").insert({"tenant_id": tenant_id, "contact_id": contact_id}).execute().data[0]


def get_messages(tenant_id: str, conversation_id: str) -> list[dict]:
    sb = get_service_client()
    conv = sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("id", conversation_id).execute().data
    if not conv:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    if conv[0]["unread"] > 0:
        sb.table("conversations").update({"unread": 0}).eq("id", conversation_id).execute()
    return (
        sb.table("messages")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
        .data
    )


def _send_via_evolution(phone: str, text: str) -> None:
    settings = get_settings()
    if not settings.evolution_api_url:
        return  # ambiente sem EvolutionAPI configurada (dev/test) — envio real fica no-op
    httpx.post(
        f"{settings.evolution_api_url}/message/sendText",
        headers={"apikey": settings.evolution_api_key},
        json={"number": phone, "text": text},
        timeout=10,
    )


def send_message(tenant_id: str, conversation_id: str, text: str, author_id: str) -> dict:
    sb = get_service_client()
    # conversation_id já é escopado por tenant_id na query abaixo — não há outro
    # id de propriedade externa aceito diretamente do cliente nesta função, então
    # não há necessidade de um verify_owned_by_tenant adicional aqui.
    conv = sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("id", conversation_id).execute().data
    if not conv:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    contact = sb.table("contacts").select("whatsapp").eq("id", conv[0]["contact_id"]).execute().data[0]

    message = (
        sb.table("messages")
        .insert({"tenant_id": tenant_id, "conversation_id": conversation_id, "direction": "out", "text": text, "author_id": author_id})
        .execute()
        .data[0]
    )
    now = datetime.now(UTC).isoformat()
    sb.table("contacts").update({"last_interaction_at": now}).eq("id", conv[0]["contact_id"]).execute()
    sb.table("activities").insert(
        {"tenant_id": tenant_id, "contact_id": conv[0]["contact_id"], "user_id": author_id, "type": "mensagem", "description": "Mensagem enviada."}
    ).execute()
    _send_via_evolution(contact["whatsapp"], text)
    return message


def update_assignee(tenant_id: str, conversation_id: str, assignee_id: str | None) -> dict:
    sb = get_service_client()
    # assignee_id é outra referência a um recurso escopado por tenant
    # (user_profiles) vinda direto do body do cliente — mesma disciplina de
    # verify_owned_by_tenant aplicada a owner_id em deals (Task 6) e a
    # supplier_id em suppliers (Task 7). None (desatribuir) não precisa checagem.
    if assignee_id is not None:
        verify_owned_by_tenant("user_profiles", assignee_id, tenant_id, "Usuário responsável não encontrado.")
    rows = (
        sb.table("conversations")
        .update({"assignee_id": assignee_id})
        .eq("tenant_id", tenant_id)
        .eq("id", conversation_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    return rows[0]
