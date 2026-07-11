from tests.conftest import auth_headers


def test_me_com_token_de_gestor(client, gestor_token, test_tenant):
    response = client.get("/api/v1/auth/me", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "gestor"
    assert body["tenant_id"] == test_tenant["id"]


def test_me_sem_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"


def test_admin_impersonando_tenant_via_header(client, admin_token, test_tenant):
    headers = {**auth_headers(admin_token), "X-Impersonate-Tenant": test_tenant["id"]}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "gestor"
    assert body["tenant_id"] == test_tenant["id"]


def test_gestor_nao_consegue_impersonar(client, gestor_token, test_tenant):
    # Só admin_saas pode "vestir" outro tenant via header — um gestor
    # mandando o mesmo header não tem nenhum efeito, seu contexto real
    # (próprio tenant) é usado normalmente.
    headers = {**auth_headers(gestor_token), "X-Impersonate-Tenant": "00000000-0000-0000-0000-000000000000"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "gestor"
    assert body["tenant_id"] == test_tenant["id"]
