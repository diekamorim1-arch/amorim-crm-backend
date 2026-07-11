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


def test_gestor_edita_nome_e_email_de_membro_da_equipe(client, gestor_token, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        novo_email = f"editado.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br"
        response = client.patch(
            f"/api/v1/users/{user_id}",
            json={"name": "Nome Editado", "email": novo_email},
            headers=auth_headers(gestor_token),
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Nome Editado"

        updated_auth_user = sb.auth.admin.get_user_by_id(user_id)
        assert updated_auth_user.user.email == novo_email
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_gestor_desativa_e_reativa_membro_da_equipe(client, gestor_token, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        deactivated = client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"is_active": False},
            headers=auth_headers(gestor_token),
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False

        reactivated = client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"is_active": True},
            headers=auth_headers(gestor_token),
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["is_active"] is True
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_gestor_nao_desativa_a_propria_conta(client, gestor_token, gestor_user_id):
    response = client.patch(
        f"/api/v1/users/{gestor_user_id}/status",
        json={"is_active": False},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 400


def test_gestor_nao_exclui_a_propria_conta(client, gestor_token, gestor_user_id):
    response = client.delete(f"/api/v1/users/{gestor_user_id}", headers=auth_headers(gestor_token))
    assert response.status_code == 400


def test_gestor_exclui_membro_sem_vinculo(client, gestor_token, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    response = client.delete(f"/api/v1/users/{user_id}", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    assert sb.table("user_profiles").select("id").eq("id", user_id).execute().data == []


def test_gestor_nao_exclui_membro_com_negocio_atribuido(client, gestor_token, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    contact = sb.table("contacts").insert(
        {
            "tenant_id": test_tenant["id"], "name": "Cliente Vinculo", "whatsapp": "+5511900001234",
            "origin": "outro", "owner_id": user_id,
        }
    ).execute().data[0]
    try:
        response = client.delete(f"/api/v1/users/{user_id}", headers=auth_headers(gestor_token))
        assert response.status_code == 409

        still_there = sb.table("user_profiles").select("id").eq("id", user_id).execute().data
        assert len(still_there) == 1
    finally:
        sb.table("contacts").delete().eq("id", contact["id"]).execute()
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_gestor_nao_edita_membro_de_outro_tenant(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Users Edit", "slug": f"alheia-users-edit-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "atendente")
        try:
            response = client.patch(
                f"/api/v1/users/{foreign_user_id}",
                json={"name": "Nome Invasor"},
                headers=auth_headers(gestor_token),
            )
            assert response.status_code == 404
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_usuario_atualiza_o_proprio_nome_via_me(client, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        response = client.patch("/api/v1/users/me", json={"name": "Nome Atualizado"}, headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["name"] == "Nome Atualizado"

        persisted = sb.table("user_profiles").select("name").eq("id", user_id).execute().data[0]
        assert persisted["name"] == "Nome Atualizado"
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_admin_saas_atualiza_o_proprio_nome_via_me(client):
    # /users/me não pode depender de tenant_id — admin_saas não tem nenhum.
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, None, "admin_saas")
    try:
        response = client.patch("/api/v1/users/me", json={"name": "Admin Renomeado"}, headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["name"] == "Admin Renomeado"
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_usuario_faz_upload_do_proprio_avatar(client, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    avatar_url = None
    try:
        response = client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("foto.png", b"fake-png-bytes", "image/png")},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        body = response.json()
        avatar_url = body["avatar_url"]
        assert avatar_url is not None
        assert avatar_url.startswith("http")

        persisted = sb.table("user_profiles").select("avatar_url").eq("id", user_id).execute().data[0]
        assert persisted["avatar_url"] == avatar_url
    finally:
        # Sem endpoint de exclusão de avatar — limpa o Storage aqui pra não
        # deixar arquivo de teste acumulando no bucket a cada run da suíte.
        if avatar_url:
            storage_path = avatar_url.split("/avatars/")[-1]
            sb.storage.from_("avatars").remove([storage_path])
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_upload_de_avatar_rejeita_tipo_nao_permitido(client, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        response = client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("script.js", b"alert(1)", "application/javascript")},
            headers=auth_headers(token),
        )
        assert response.status_code == 415
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_usuario_marca_notificacoes_como_vistas(client, test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    try:
        before = sb.table("user_profiles").select("notifications_last_seen_at").eq("id", user_id).execute().data[0]
        assert before["notifications_last_seen_at"] is None

        response = client.post("/api/v1/users/me/notifications-seen", headers=auth_headers(token))
        assert response.status_code == 200
        assert response.json()["notifications_last_seen_at"] is not None

        after = sb.table("user_profiles").select("notifications_last_seen_at").eq("id", user_id).execute().data[0]
        assert after["notifications_last_seen_at"] is not None
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
