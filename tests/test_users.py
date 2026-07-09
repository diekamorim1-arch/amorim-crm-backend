import uuid

from tests.conftest import _create_user_and_sign_in, auth_headers
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


def test_convite_com_role_admin_saas_e_rejeitado_pelo_pydantic(client, gestor_token):
    # Critical do whole-branch review: um gestor não pode se auto-promover (ou
    # promover outro usuário) a admin_saas via /users/invite. UserInvite.role
    # é Literal["atendente", "gestor"], então o Pydantic já rejeita com 422
    # antes de qualquer lógica de serviço rodar — nenhum usuário chega a ser
    # criado no Supabase Auth.
    response = client.post(
        "/api/v1/users/invite",
        json={"name": "Tentativa Escalonamento", "email": f"escalada.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br", "role": "admin_saas"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 422


def test_atualizar_role_para_admin_saas_e_rejeitado_pelo_pydantic(client, gestor_token, test_tenant):
    # Mesmo Critical, mas via PATCH /users/{id}/role sobre um usuário real
    # (atendente) do próprio tenant: UserRoleUpdate.role também é Literal,
    # então o 422 acontece antes de update_role ser chamado.
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        response = client.patch(
            f"/api/v1/users/{user_id}/role",
            json={"role": "admin_saas"},
            headers=auth_headers(gestor_token),
        )
        assert response.status_code == 422

        unchanged = sb.table("user_profiles").select("role").eq("id", user_id).execute().data[0]
        assert unchanged["role"] == "atendente"
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_gestor_nao_altera_role_de_usuario_de_outro_tenant(client, gestor_token):
    # Critical do whole-branch review, segunda metade: update_role não tinha
    # NENHUMA guarda de tenant — um gestor do test_tenant podia alterar a role
    # de um user_id de qualquer outro tenant. Cria um tenant + atendente real
    # em OUTRO tenant e confirma 404 + role inalterada.
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Users", "slug": f"alheia-users-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "atendente")
        try:
            response = client.patch(
                f"/api/v1/users/{foreign_user_id}/role",
                json={"role": "gestor"},
                headers=auth_headers(gestor_token),
            )
            assert response.status_code == 404

            unchanged = sb.table("user_profiles").select("role").eq("id", foreign_user_id).execute().data[0]
            assert unchanged["role"] == "atendente"
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
