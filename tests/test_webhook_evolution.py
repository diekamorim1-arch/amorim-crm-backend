import hashlib
import hmac
import json

from app.config import get_settings
from app.core.supabase_client import get_service_client


def _signed_post(client, payload: dict):
    body = json.dumps(payload).encode()
    secret = get_settings().evolution_webhook_secret.encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/v1/webhooks/evolution",
        content=body,
        headers={"Content-Type": "application/json", "x-evolution-signature": signature},
    )


def test_assinatura_invalida_rejeita_com_401(client):
    response = client.post(
        "/api/v1/webhooks/evolution",
        content=b'{"event":"connection.update","instance":"x","data":{"state":"open"}}',
        headers={"Content-Type": "application/json", "x-evolution-signature": "assinatura-errada"},
    )
    assert response.status_code == 401


def test_connection_update_open_marca_conectado_e_seta_connected_at(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000009"})
        .execute()
        .data[0]
    )
    try:
        response = _signed_post(
            client, {"event": "connection.update", "instance": connection["id"], "data": {"state": "open"}}
        )
        assert response.status_code == 200

        updated = sb.table("connections").select("*").eq("id", connection["id"]).execute().data[0]
        assert updated["status"] == "conectado"
        assert updated["connected_at"] is not None
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_connection_update_close_marca_desconectado(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert(
            {
                "tenant_id": test_tenant["id"],
                "user_id": gestor_user_id,
                "phone": "+5511000000010",
                "status": "conectado",
            }
        )
        .execute()
        .data[0]
    )
    try:
        response = _signed_post(
            client, {"event": "connection.update", "instance": connection["id"], "data": {"state": "close"}}
        )
        assert response.status_code == 200

        updated = sb.table("connections").select("status").eq("id", connection["id"]).execute().data[0]
        assert updated["status"] == "desconectado"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_connection_update_estado_desconhecido_e_ignorado_sem_erro(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000011"})
        .execute()
        .data[0]
    )
    try:
        response = _signed_post(
            client, {"event": "connection.update", "instance": connection["id"], "data": {"state": "refused"}}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

        unchanged = sb.table("connections").select("status").eq("id", connection["id"]).execute().data[0]
        assert unchanged["status"] == "desconectado"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()
