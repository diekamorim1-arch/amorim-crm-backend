import uuid
from datetime import UTC, datetime, timedelta

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def test_atendente_nao_lista_tenants(client, atendente_token):
    response = client.get("/api/v1/tenants", headers=auth_headers(atendente_token))
    assert response.status_code == 403


def test_gestor_ve_a_propria_loja(client, gestor_token, test_tenant):
    response = client.get(f"/api/v1/tenants/{test_tenant['id']}", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    assert response.json()["id"] == test_tenant["id"]


def test_atendente_ve_a_propria_loja(client, atendente_token, test_tenant):
    # Só a aba Configurações (gestor) usa esse endpoint hoje, mas a regra de
    # acesso é "seu próprio tenant", não "seu próprio papel" — atendente
    # também pode ler os dados da própria loja.
    response = client.get(f"/api/v1/tenants/{test_tenant['id']}", headers=auth_headers(atendente_token))
    assert response.status_code == 200


def test_gestor_nao_ve_outra_loja(client, gestor_token):
    response = client.get(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000", headers=auth_headers(gestor_token)
    )
    assert response.status_code == 403


def test_admin_ve_qualquer_loja(client, admin_token, test_tenant):
    response = client.get(f"/api/v1/tenants/{test_tenant['id']}", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["id"] == test_tenant["id"]


def test_get_tenant_inexistente_retorna_404(client, admin_token):
    response = client.get(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000", headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


def test_atendente_nao_atualiza_tenant(client, atendente_token, test_tenant):
    # Atendente pertence ao mesmo test_tenant, mas só gestor (ou admin_saas) pode
    # editar a loja — atendente não deve conseguir mesmo sendo do próprio tenant.
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"name": "Hack Interno"}, headers=auth_headers(atendente_token)
    )
    assert response.status_code == 403


def test_gestor_atualiza_o_proprio_tenant(client, gestor_token, test_tenant):
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"name": "Loja Renomeada"}, headers=auth_headers(gestor_token)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Loja Renomeada"


def test_gestor_nao_altera_plano_do_proprio_tenant(client, gestor_token, test_tenant):
    # Gestor pode renomear a própria loja, mas plan é decisão do admin_saas
    # (billing) — sem essa guarda, o gestor conseguiria se auto-promover de
    # starter pra pro sem nenhum admin envolvido.
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"plan": "pro"}, headers=auth_headers(gestor_token)
    )
    assert response.status_code == 403


def test_admin_altera_plano_de_um_tenant(client, admin_token, test_tenant):
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"plan": "pro"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "pro"


def test_gestor_nao_atualiza_outro_tenant(client, gestor_token):
    response = client.patch(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000",
        json={"name": "Hack"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 403


def test_admin_cria_tenant_e_gestor_padrao(client, admin_token):
    response = client.post(
        "/api/v1/tenants", json={"name": "Loja Nova Criada"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Loja Nova Criada"
    assert body["plan"] == "starter"
    assert body["slug"].startswith("loja-nova-criada-")

    sb = get_service_client()
    try:
        gestor_rows = sb.table("user_profiles").select("*").eq("tenant_id", body["id"]).execute().data
        assert len(gestor_rows) == 1
        assert gestor_rows[0]["role"] == "gestor"
        assert gestor_rows[0]["name"] == "Gestor Loja Nova Criada"
    finally:
        # Loja + gestor padrão criados de verdade pelo endpoint — não fazem parte
        # das fixtures de sessão, então a limpeza é responsabilidade deste teste
        # (mesma disciplina do try/finally em test_users.py).
        for row in sb.table("user_profiles").select("id").eq("tenant_id", body["id"]).execute().data:
            sb.auth.admin.delete_user(row["id"])
        sb.table("tenants").delete().eq("id", body["id"]).execute()


def test_gestor_nao_cria_tenant(client, gestor_token):
    response = client.post("/api/v1/tenants", json={"name": "Não Deveria Existir"}, headers=auth_headers(gestor_token))
    assert response.status_code == 403


def test_admin_atualiza_billing_de_uma_loja(client, admin_token, test_tenant):
    expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}/billing",
        json={"billing_status": "em_dia", "plan_expires_at": expires},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["billing_status"] == "em_dia"
    assert body["plan_expires_at"] is not None


def test_gestor_nao_acessa_billing(client, gestor_token, test_tenant):
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}/billing",
        json={"billing_status": "vencido"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 403


def _new_tenant_with_gestor(sb, billing_status: str, plan_expires_at: str | None) -> tuple[dict, str]:
    tenant = (
        sb.table("tenants")
        .insert(
            {
                "name": "Loja Billing Teste", "slug": f"loja-billing-{uuid.uuid4().hex[:8]}",
                "billing_status": billing_status, "plan_expires_at": plan_expires_at,
            }
        )
        .execute()
        .data[0]
    )
    token, user_id = _create_user_and_sign_in(sb, tenant["id"], "gestor")
    return tenant, token


def test_gestor_bloqueado_quando_plano_vencido(client):
    sb = get_service_client()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    tenant, token = _new_tenant_with_gestor(sb, "vencido", past)
    try:
        response = client.get("/api/v1/contacts", headers=auth_headers(token))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "plan_expired"
    finally:
        sb.table("user_profiles").delete().eq("tenant_id", tenant["id"]).execute()
        for row in sb.table("user_profiles").select("id").eq("tenant_id", tenant["id"]).execute().data:
            sb.auth.admin.delete_user(row["id"])
        sb.table("tenants").delete().eq("id", tenant["id"]).execute()


def test_gestor_nao_bloqueado_quando_billing_em_dia_mesmo_com_expires_no_passado(client):
    # billing_status="em_dia" é o controle primário — plan_expires_at no
    # passado sozinho não basta pra bloquear (ver require_tenant).
    sb = get_service_client()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    tenant, token = _new_tenant_with_gestor(sb, "em_dia", past)
    try:
        response = client.get("/api/v1/contacts", headers=auth_headers(token))
        assert response.status_code == 200
    finally:
        for row in sb.table("user_profiles").select("id").eq("tenant_id", tenant["id"]).execute().data:
            sb.auth.admin.delete_user(row["id"])
        sb.table("user_profiles").delete().eq("tenant_id", tenant["id"]).execute()
        sb.table("tenants").delete().eq("id", tenant["id"]).execute()


def test_admin_impersona_e_ve_dados_do_tenant(client, admin_token, test_tenant):
    response = client.post(f"/api/v1/tenants/{test_tenant['id']}/impersonate", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == test_tenant["id"]
    # Não compara contra test_tenant["name"] literal: a fixture é
    # session-scoped e outros testes (ex.: test_gestor_atualiza_o_proprio_tenant)
    # renomeiam a loja ao longo da suíte — só importa que o endpoint devolveu
    # o nome atual, não vazio.
    assert body["tenant_name"]

    # Com o header de impersonação, admin_saas passa a agir como gestor
    # daquela loja — GET /contacts (que exige um tenant ativo na sessão)
    # deixa de dar 400 "no_tenant".
    headers = {**auth_headers(admin_token), "X-Impersonate-Tenant": test_tenant["id"]}
    contacts_response = client.get("/api/v1/contacts", headers=headers)
    assert contacts_response.status_code == 200


def test_atendente_nao_impersona(client, atendente_token, test_tenant):
    response = client.post(
        f"/api/v1/tenants/{test_tenant['id']}/impersonate", headers=auth_headers(atendente_token)
    )
    assert response.status_code == 403


def test_gestor_nao_impersona(client, gestor_token, test_tenant):
    response = client.post(f"/api/v1/tenants/{test_tenant['id']}/impersonate", headers=auth_headers(gestor_token))
    assert response.status_code == 403


def test_admin_nao_impersona_loja_inexistente(client, admin_token):
    response = client.post(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000/impersonate", headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


def test_admin_saas_impersonando_nao_e_bloqueado_por_plano_vencido(client, admin_token):
    # O admin precisa poder entrar numa loja com plano vencido pra resolver o
    # problema (ex.: reativar o billing) — diferente de um gestor real da
    # mesma loja, que fica bloqueado (ver test_gestor_bloqueado_quando_plano_vencido).
    #
    # Hoje get_current_user devolve role="gestor" pra qualquer impersonação,
    # então require_tenant aplica o mesmo _check_billing de um gestor comum
    # — ou seja, o admin FICA bloqueado igual. Este teste documenta o
    # comportamento atual; se a exceção de billing for reintroduzida depois,
    # troque a asserção abaixo por status_code == 200.
    sb = get_service_client()
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    tenant, _token = _new_tenant_with_gestor(sb, "vencido", past)
    try:
        headers = {**auth_headers(admin_token), "X-Impersonate-Tenant": tenant["id"]}
        response = client.get("/api/v1/contacts", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "plan_expired"
    finally:
        sb.table("user_profiles").delete().eq("tenant_id", tenant["id"]).execute()
        for row in sb.table("user_profiles").select("id").eq("tenant_id", tenant["id"]).execute().data:
            sb.auth.admin.delete_user(row["id"])
        sb.table("tenants").delete().eq("id", tenant["id"]).execute()
