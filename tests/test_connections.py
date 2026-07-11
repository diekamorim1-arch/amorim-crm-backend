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


def test_atendente_pareia_e_desconecta_a_propria_conexao(client, atendente_token, atendente_user_id, test_tenant):
    # Complementa test_pair_e_disconnect_atualizam_status (que só cobre
    # gestor): confirma que um atendente consegue parear/desconectar a
    # PRÓPRIA conexão, já que a checagem de posse em _assert_can_manage só
    # bloqueia quando o dono da conexão é outro usuário.
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": atendente_user_id, "phone": "+5511000000004"})
        .execute()
        .data[0]
    )
    try:
        paired = client.post(f"/api/v1/connections/{connection['id']}/pair", headers=auth_headers(atendente_token))
        assert paired.status_code == 200
        assert paired.json()["status"] == "pareando"

        disconnected = client.post(
            f"/api/v1/connections/{connection['id']}/disconnect", headers=auth_headers(atendente_token)
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "desconectado"
    finally:
        _cleanup_connections([connection["id"]])


def test_atendente_nao_gerencia_conexao_de_outro_usuario(client, atendente_token, test_tenant):
    """Correção pós-revisão: `_get_connection` só escopava por tenant_id, então
    um atendente conseguia parear/desconectar a conexão de QUALQUER usuário do
    mesmo tenant, não só a própria — violando o access model "atendente
    (a própria), gestor (any)". Cria um segundo usuário real no mesmo tenant
    com sua própria conexão e confirma que o primeiro atendente recebe 403 ao
    tentar pair/disconnect nela."""
    sb = get_service_client()
    other_token, other_user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        other_connection = (
            sb.table("connections")
            .insert({"tenant_id": test_tenant["id"], "user_id": other_user_id, "phone": "+5511000000005"})
            .execute()
            .data[0]
        )
        try:
            pair_response = client.post(
                f"/api/v1/connections/{other_connection['id']}/pair", headers=auth_headers(atendente_token)
            )
            assert pair_response.status_code == 403

            disconnect_response = client.post(
                f"/api/v1/connections/{other_connection['id']}/disconnect", headers=auth_headers(atendente_token)
            )
            assert disconnect_response.status_code == 403

            unchanged = sb.table("connections").select("status").eq("id", other_connection["id"]).execute().data[0]
            assert unchanged["status"] == "desconectado"
        finally:
            sb.table("connections").delete().eq("id", other_connection["id"]).execute()
    finally:
        sb.table("user_profiles").delete().eq("id", other_user_id).execute()
        sb.auth.admin.delete_user(other_user_id)


def test_cria_a_propria_conexao(client, gestor_token, gestor_user_id, test_tenant):
    response = client.post(
        "/api/v1/connections", json={"phone": "+5511000000006"}, headers=auth_headers(gestor_token)
    )
    try:
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == gestor_user_id
        assert body["phone"] == "+5511000000006"
        assert body["status"] == "desconectado"
    finally:
        _cleanup_connections([response.json()["id"]] if response.status_code == 200 else [])


def test_nao_cria_segunda_conexao_pro_mesmo_usuario(client, gestor_token, gestor_user_id, test_tenant):
    sb = get_service_client()
    existing = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000007"})
        .execute()
        .data[0]
    )
    try:
        response = client.post(
            "/api/v1/connections", json={"phone": "+5511000000008"}, headers=auth_headers(gestor_token)
        )
        assert response.status_code == 409
    finally:
        _cleanup_connections([existing["id"]])


def test_qrcode_retorna_503_quando_evolution_nao_configurada(client, gestor_token, gestor_user_id, test_tenant):
    # Este ambiente de teste roda com EVOLUTION_API_URL vazio (mesmo padrão
    # de test_pair_e_disconnect_atualizam_status) — get_qrcode não tem um
    # caminho no-op como pair/disconnect porque não existe QR nenhum pra
    # devolver sem a Evolution de verdade, então o correto aqui é 503, não
    # um 200 com dado inventado.
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000012"})
        .execute()
        .data[0]
    )
    try:
        response = client.get(f"/api/v1/connections/{connection['id']}/qrcode", headers=auth_headers(gestor_token))
        assert response.status_code == 503
    finally:
        _cleanup_connections([connection["id"]])


def test_send_message_retorna_503_quando_evolution_nao_configurada(client, gestor_token, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000013"})
        .execute()
        .data[0]
    )
    try:
        response = client.post(
            f"/api/v1/connections/{connection['id']}/messages",
            json={"number": "+5511988887777", "text": "oi"},
            headers=auth_headers(gestor_token),
        )
        assert response.status_code == 503
    finally:
        _cleanup_connections([connection["id"]])


def test_deleta_a_propria_conexao_e_libera_criar_outra(client, gestor_token, gestor_user_id, test_tenant):
    """Cobre o pedido de produto "criar um novo login na Evolution API quando
    eu quiser": sem delete, um usuário preso com uma conexão com número
    errado (ou instância travada do lado da Evolution) nunca conseguia
    recomeçar, porque create_connection bloqueia uma segunda conexão pro
    mesmo usuário (409, ver test_nao_cria_segunda_conexao_pro_mesmo_usuario).
    """
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000020"})
        .execute()
        .data[0]
    )
    deleted = client.delete(f"/api/v1/connections/{connection['id']}", headers=auth_headers(gestor_token))
    assert deleted.status_code == 200
    assert sb.table("connections").select("id").eq("id", connection["id"]).execute().data == []

    recreated = client.post(
        "/api/v1/connections", json={"phone": "+5511000000021"}, headers=auth_headers(gestor_token)
    )
    try:
        assert recreated.status_code == 200
        assert recreated.json()["phone"] == "+5511000000021"
    finally:
        _cleanup_connections([recreated.json()["id"]] if recreated.status_code == 200 else [])


def test_atendente_nao_deleta_conexao_de_outro_usuario(client, atendente_token, test_tenant):
    sb = get_service_client()
    other_token, other_user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        other_connection = (
            sb.table("connections")
            .insert({"tenant_id": test_tenant["id"], "user_id": other_user_id, "phone": "+5511000000022"})
            .execute()
            .data[0]
        )
        try:
            response = client.delete(
                f"/api/v1/connections/{other_connection['id']}", headers=auth_headers(atendente_token)
            )
            assert response.status_code == 403
            assert sb.table("connections").select("id").eq("id", other_connection["id"]).execute().data != []
        finally:
            sb.table("connections").delete().eq("id", other_connection["id"]).execute()
    finally:
        sb.table("user_profiles").delete().eq("id", other_user_id).execute()
        sb.auth.admin.delete_user(other_user_id)


def test_delete_rejeita_connection_id_de_outro_tenant(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Delete", "slug": f"alheia-del-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_connection = (
                sb.table("connections")
                .insert({"tenant_id": foreign_tenant["id"], "user_id": foreign_user_id, "phone": "+5511977770001"})
                .execute()
                .data[0]
            )
            try:
                response = client.delete(
                    f"/api/v1/connections/{foreign_connection['id']}", headers=auth_headers(gestor_token)
                )
                assert response.status_code == 404
            finally:
                sb.table("connections").delete().eq("id", foreign_connection["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


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
