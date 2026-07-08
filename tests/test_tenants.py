from tests.conftest import auth_headers


def test_atendente_nao_lista_tenants(client, atendente_token):
    response = client.get("/api/v1/tenants", headers=auth_headers(atendente_token))
    assert response.status_code == 403


def test_gestor_atualiza_o_proprio_tenant(client, gestor_token, test_tenant):
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"name": "Loja Renomeada"}, headers=auth_headers(gestor_token)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Loja Renomeada"


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
