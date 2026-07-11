import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.errors import AppError
from app.core.supabase_client import get_service_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# Evolution manda "state" em inglês (Baileys); mapeamos pro enum em
# português já usado em connections.status. Estados sem correspondência
# (ex.: "refused") são ignorados em vez de forçar um valor errado.
_CONNECTION_STATE_MAP = {"open": "conectado", "connecting": "pareando", "close": "desconectado"}


def _handle_connection_update(connection: dict, payload: dict) -> dict:
    state = (payload.get("data") or {}).get("state")
    status = _CONNECTION_STATE_MAP.get(state)
    if not status:
        return {"status": "ignored"}

    sb = get_service_client()
    patch: dict = {"status": status}
    if status == "conectado":
        patch["connected_at"] = datetime.now(UTC).isoformat()
    sb.table("connections").update(patch).eq("id", connection["id"]).execute()
    return {"status": "processed"}


def _digits_only(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


def _handle_message(connection: dict, payload: dict) -> dict:
    data = payload.get("data") or {}
    key = data.get("key") or {}
    if key.get("fromMe"):
        # Mensagem que a própria loja enviou (ex.: pelo app oficial do
        # WhatsApp, fora do CRM) — não é uma mensagem recebida de cliente.
        return {"status": "ignored"}

    remote_jid = key.get("remoteJid")
    text = (data.get("message") or {}).get("conversation")
    if not remote_jid or not text:
        # Tipo de mensagem que ainda não suportamos (imagem, áudio, figurinha
        # etc. não têm "conversation") — ignora em vez de falhar.
        return {"status": "ignored"}

    # remoteJid vem no formato "5511999998888@s.whatsapp.net"; contacts.whatsapp
    # não tem formato garantido (livre na criação do contato), então comparamos
    # só os dígitos em vez de exigir bater caractere a caractere.
    from_number = _digits_only(remote_jid.split("@")[0])
    tenant_id = connection["tenant_id"]

    sb = get_service_client()
    contacts = sb.table("contacts").select("*").eq("tenant_id", tenant_id).execute().data
    contact = next((c for c in contacts if _digits_only(c["whatsapp"]) == from_number), None)
    if not contact:
        raise AppError(404, "unknown_contact", "Remetente não corresponde a nenhum cliente cadastrado.")

    conversation = (
        sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("contact_id", contact["id"]).execute().data
    )
    if conversation:
        conversation = conversation[0]
    else:
        conversation = sb.table("conversations").insert({"tenant_id": tenant_id, "contact_id": contact["id"]}).execute().data[0]

    sb.table("messages").insert(
        {"tenant_id": tenant_id, "conversation_id": conversation["id"], "direction": "in", "text": text}
    ).execute()
    sb.table("conversations").update({"unread": conversation["unread"] + 1}).eq("id", conversation["id"]).execute()
    now = datetime.now(UTC).isoformat()
    sb.table("contacts").update({"last_interaction_at": now}).eq("id", contact["id"]).execute()
    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": contact["id"],
            "user_id": conversation.get("assignee_id") or contact["owner_id"],
            "type": "mensagem", "description": "Mensagem recebida.",
        }
    ).execute()
    return {"status": "processed"}


@router.post("/evolution")
async def receive_evolution_webhook(request: Request):
    payload = await request.json()

    # connection_id é reaproveitado como instanceName da Evolution (ver
    # pair() em connections/service.py) — o próprio nome da instância já É o
    # id da linha em connections, sem tabela de mapeamento à parte.
    instance_id = payload.get("instance")
    apikey = payload.get("apikey")
    if not instance_id or not apikey:
        raise AppError(400, "invalid_payload", "Payload do webhook malformado.")

    sb = get_service_client()
    rows = sb.table("connections").select("*").eq("id", instance_id).execute().data
    stored_token = rows[0].get("evolution_token") if rows else None
    # "instância não encontrada" e "token não bate" caem no mesmo 401 em vez
    # de 404 + 401 — não vale a pena dar a um chamador não autenticado uma
    # forma de descobrir quais ids de conexão existem.
    if not stored_token or not hmac.compare_digest(stored_token, apikey):
        raise AppError(401, "invalid_signature", "Token do webhook inválido.")
    connection = rows[0]

    event = payload.get("event")
    if event == "connection.update":
        return _handle_connection_update(connection, payload)
    if event == "messages.upsert":
        return _handle_message(connection, payload)
    return {"status": "ignored"}
