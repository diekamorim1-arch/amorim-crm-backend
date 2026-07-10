import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature: str) -> None:
    settings = get_settings()
    expected = hmac.new(settings.evolution_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AppError(401, "invalid_signature", "Assinatura do webhook inválida.")


# Evolution manda "state" em inglês (Baileys); mapeamos pro enum em
# português já usado em connections.status. Estados sem correspondência
# (ex.: "refused") são ignorados em vez de forçar um valor errado.
_CONNECTION_STATE_MAP = {"open": "conectado", "connecting": "pareando", "close": "desconectado"}


def _handle_connection_update(payload: dict) -> dict:
    # connection_id é reaproveitado como instanceName da Evolution (mesma
    # convenção de connections/service.py:pair) — o próprio nome da instância
    # já É o id da linha em connections, sem tabela de mapeamento à parte.
    connection_id = payload.get("instance")
    state = (payload.get("data") or {}).get("state")
    status = _CONNECTION_STATE_MAP.get(state)
    if not connection_id or not status:
        return {"status": "ignored"}

    sb = get_service_client()
    patch: dict = {"status": status}
    if status == "conectado":
        patch["connected_at"] = datetime.now(UTC).isoformat()
    sb.table("connections").update(patch).eq("id", connection_id).execute()
    return {"status": "processed"}


@router.post("/evolution")
async def receive_evolution_webhook(request: Request, x_evolution_signature: str = Header(default="")):
    raw_body = await request.body()
    _verify_signature(raw_body, x_evolution_signature)
    payload = await request.json()

    if payload.get("event") == "connection.update":
        return _handle_connection_update(payload)

    try:
        instance_phone = payload["instance"]["phone"]
        from_number = payload["message"]["from"]
        text = payload["message"]["text"]
    except (KeyError, TypeError) as exc:
        raise AppError(400, "invalid_payload", "Payload do webhook malformado.") from exc

    sb = get_service_client()
    connection = sb.table("connections").select("*").eq("phone", instance_phone).execute().data
    if not connection:
        raise AppError(404, "unknown_instance", "Conexão do WhatsApp não encontrada para este número.")
    tenant_id = connection[0]["tenant_id"]

    contact = sb.table("contacts").select("*").eq("tenant_id", tenant_id).eq("whatsapp", from_number).execute().data
    if not contact:
        raise AppError(404, "unknown_contact", "Remetente não corresponde a nenhum cliente cadastrado.")
    contact = contact[0]

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
