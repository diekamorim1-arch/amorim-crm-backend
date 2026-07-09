from app.core.supabase_client import get_service_client
from tests.conftest import auth_headers


def test_atendente_nao_lista_tenants(client, atendente_token):
    response = client.get("/api/v1/tenants", headers=auth_headers(atendente_token))
    assert response.status_code == 403


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


def test_admin_impersona_e_ve_dados_do_tenant(client, admin_token, gestor_token, test_tenant):
    impersonate = client.post(f"/api/v1/tenants/{test_tenant['id']}/impersonate", headers=auth_headers(admin_token))
    assert impersonate.status_code == 200
    assert impersonate.json()["tenant_id"] == test_tenant["id"]

    as_gestor_via_impersonation = client.get(
        "/api/v1/tenants", headers={**auth_headers(admin_token), "X-Impersonate-Tenant": test_tenant["id"]}
    )
    # role vira "gestor" ao impersonar — perde acesso ao endpoint admin_saas-only.
    assert as_gestor_via_impersonation.status_code == 403


def test_atendente_nao_impersona(client, atendente_token, test_tenant):
    response = client.post(f"/api/v1/tenants/{test_tenant['id']}/impersonate", headers=auth_headers(atendente_token))
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
