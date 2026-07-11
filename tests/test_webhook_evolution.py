from app.core.supabase_client import get_service_client

# A Evolution API v2.1.1 não assina o corpo do webhook (sem HMAC) — o único
# jeito de provar que um evento veio da instância certa é o token por-conexão
# (connections.evolution_token, gerado em pair() a partir do campo "hash" de
# POST /instance/create) ecoado de volta no campo "apikey" de todo evento.
TOKEN = "token-de-teste-da-instancia"


def _connection_with_token(sb, tenant_id: str, user_id: str, phone: str, **extra) -> dict:
    return (
        sb.table("connections")
        .insert({"tenant_id": tenant_id, "user_id": user_id, "phone": phone, "evolution_token": TOKEN, **extra})
        .execute()
        .data[0]
    )


def test_token_invalido_rejeita_com_401(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = _connection_with_token(sb, test_tenant["id"], gestor_user_id, "+5511000000008")
    try:
        response = client.post(
            "/api/v1/webhooks/evolution",
            json={"event": "connection.update", "instance": connection["id"], "apikey": "token-errado", "data": {"state": "open"}},
        )
        assert response.status_code == 401
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_instancia_desconhecida_rejeita_com_401(client):
    # "não encontrada" e "token errado" caem no mesmo 401 — não vale a pena
    # dar a um chamador não autenticado uma forma de descobrir quais ids de
    # conexão existem (ver comentário em app/webhooks/evolution.py).
    response = client.post(
        "/api/v1/webhooks/evolution",
        json={"event": "connection.update", "instance": "00000000-0000-0000-0000-000000000000", "apikey": "qualquer", "data": {"state": "open"}},
    )
    assert response.status_code == 401


def test_payload_sem_instance_ou_apikey_retorna_400(client):
    response = client.post("/api/v1/webhooks/evolution", json={"event": "connection.update", "data": {"state": "open"}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"


def test_connection_update_open_marca_conectado_e_seta_connected_at(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = _connection_with_token(sb, test_tenant["id"], gestor_user_id, "+5511000000009")
    try:
        response = client.post(
            "/api/v1/webhooks/evolution",
            json={"event": "connection.update", "instance": connection["id"], "apikey": TOKEN, "data": {"state": "open"}},
        )
        assert response.status_code == 200

        updated = sb.table("connections").select("*").eq("id", connection["id"]).execute().data[0]
        assert updated["status"] == "conectado"
        assert updated["connected_at"] is not None
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_connection_update_close_marca_desconectado(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = _connection_with_token(sb, test_tenant["id"], gestor_user_id, "+5511000000010", status="conectado")
    try:
        response = client.post(
            "/api/v1/webhooks/evolution",
            json={"event": "connection.update", "instance": connection["id"], "apikey": TOKEN, "data": {"state": "close"}},
        )
        assert response.status_code == 200

        updated = sb.table("connections").select("status").eq("id", connection["id"]).execute().data[0]
        assert updated["status"] == "desconectado"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_connection_update_estado_desconhecido_e_ignorado_sem_erro(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = _connection_with_token(sb, test_tenant["id"], gestor_user_id, "+5511000000011")
    try:
        response = client.post(
            "/api/v1/webhooks/evolution",
            json={"event": "connection.update", "instance": connection["id"], "apikey": TOKEN, "data": {"state": "refused"}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

        unchanged = sb.table("connections").select("status").eq("id", connection["id"]).execute().data[0]
        assert unchanged["status"] == "desconectado"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()


def test_evento_nao_reconhecido_e_ignorado_sem_erro(client, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = _connection_with_token(sb, test_tenant["id"], gestor_user_id, "+5511000000012")
    try:
        response = client.post(
            "/api/v1/webhooks/evolution",
            json={"event": "qrcode.updated", "instance": connection["id"], "apikey": TOKEN, "data": {}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()
