import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _cleanup_connections(connection_ids: list[str]) -> None:
    sb = get_service_client()
    for connection_id in connection_ids:
        sb.table("connections").delete().eq("id", connection_id).execute()


def test_atendente_ve_so_a_propria_conexao(
    client, gestor_token, atendente_token, test_tenant, gestor_user_id, atendente_user_id
):
    sb = get_service_client()
    conn_gestor = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000001"})
        .execute()
        .data[0]
    )
    conn_atendente = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": atendente_user_id, "phone": "+5511000000002"})
        .execute()
        .data[0]
    )
    try:
        as_atendente = client.get("/api/v1/connections", headers=auth_headers(atendente_token))
        assert as_atendente.status_code == 200
        assert len(as_atendente.json()) == 1
        assert as_atendente.json()[0]["phone"] == "+5511000000002"

        as_gestor = client.get("/api/v1/connections", headers=auth_headers(gestor_token))
        assert as_gestor.status_code == 200
        assert len(as_gestor.json()) == 2
    finally:
        _cleanup_connections([conn_gestor["id"], conn_atendente["id"]])


def test_pair_e_disconnect_atualizam_status(client, gestor_token, gestor_user_id, test_tenant):
    # Confirma também que pair/disconnect não travam nem lançam exceção quando
    # `evolution_api_url` não está configurada neste ambiente de teste (mesmo
    # padrão no-op de `_send_via_evolution` na Task 8): se o branch condicional
    # tentasse chamar a EvolutionAPI de verdade aqui, o teste falharia por
    # timeout/erro de conexão em vez de passar.
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000003"})
        .execute()
        .data[0]
    )
    try:
        paired = client.post(f"/api/v1/connections/{connection['id']}/pair", headers=auth_headers(gestor_token))
        assert paired.status_code == 200
        assert paired.json()["status"] == "pareando"

        disconnected = client.post(
            f"/api/v1/connections/{connection['id']}/disconnect", headers=auth_headers(gestor_token)
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "desconectado"
    finally:
        _cleanup_connections([connection["id"]])


def test_pair_rejeita_connection_id_de_outro_tenant(client, gestor_token):
    """`_get_connection` filtra por tenant_id antes de buscar pelo id
    (ver brief), então um connection_id de outro tenant já deveria resultar em
    404 por construção. Este teste confirma essa suposição em vez de
    simplesmente aceitá-la, conforme pedido: se o filtro por tenant_id fosse
    removido ou quebrado, este teste passaria a falhar."""
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Connections", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_connection = (
                sb.table("connections")
                .insert({"tenant_id": foreign_tenant["id"], "user_id": foreign_user_id, "phone": "+5511977770000"})
                .execute()
                .data[0]
            )
            try:
                response = client.post(
                    f"/api/v1/connections/{foreign_connection['id']}/pair", headers=auth_headers(gestor_token)
                )
                assert response.status_code == 404
            finally:
                sb.table("connections").delete().eq("id", foreign_connection["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
