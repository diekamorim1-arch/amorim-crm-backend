from tests.conftest import auth_headers


def test_admin_lista_usuarios_de_todos_os_tenants_com_nome_da_loja(
    client, admin_token, gestor_token, gestor_user_id, test_tenant
):
    response = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()

    gestor_row = next(u for u in body if u["id"] == gestor_user_id)
    assert gestor_row["tenant_id"] == test_tenant["id"]
    assert gestor_row["tenant_name"] == test_tenant["name"]
    assert gestor_row["role"] == "gestor"
    assert gestor_row["email"]


def test_admin_saas_aparece_sem_tenant_name(client, admin_token, admin_user_id):
    response = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert response.status_code == 200
    admin_row = next(u for u in response.json() if u["id"] == admin_user_id)
    assert admin_row["tenant_id"] is None
    assert admin_row["tenant_name"] is None


def test_gestor_nao_acessa_admin_users(client, gestor_token):
    response = client.get("/api/v1/admin/users", headers=auth_headers(gestor_token))
    assert response.status_code == 403


def test_atendente_nao_acessa_admin_users(client, atendente_token):
    response = client.get("/api/v1/admin/users", headers=auth_headers(atendente_token))
    assert response.status_code == 403
