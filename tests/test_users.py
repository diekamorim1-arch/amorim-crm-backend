import uuid

from tests.conftest import auth_headers
from app.core.supabase_client import get_service_client


def test_gestor_convida_e_lista_usuario(client, gestor_token, test_tenant):
    email = f"novo.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br"
    invite = client.post(
        "/api/v1/users/invite",
        json={"name": "Novo Atendente", "email": email, "role": "atendente"},
        headers=auth_headers(gestor_token),
    )
    assert invite.status_code == 200
    invited_user_id = invite.json()["id"]

    try:
        listing = client.get("/api/v1/users", headers=auth_headers(gestor_token))
        assert any(u["name"] == "Novo Atendente" for u in listing.json())
    finally:
        # Usuário convidado de verdade (auth.users + user_profiles) — não faz parte
        # das fixtures de sessão, então precisa ser limpo aqui mesmo (cascade cuida
        # de user_profiles, ver Task 3).
        get_service_client().auth.admin.delete_user(invited_user_id)


def test_atendente_nao_convida(client, atendente_token):
    response = client.post(
        "/api/v1/users/invite",
        json={"name": "X", "email": "x@x.com", "role": "atendente"},
        headers=auth_headers(atendente_token),
    )
    assert response.status_code == 403
