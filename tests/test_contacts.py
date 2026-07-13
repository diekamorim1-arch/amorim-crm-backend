import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _create_contact(client, token, owner_id, **overrides):
    payload = {
        "name": "Cliente Teste",
        "whatsapp": "+5511999990000",
        "origin": "whatsapp_direto",
        "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _delete_contact(contact_id: str) -> None:
    # Contato criado de verdade pelo endpoint — não faz parte das fixtures de
    # sessão, então a limpeza é responsabilidade de cada teste (mesma
    # disciplina do try/finally em test_users.py / test_tenants.py).
    get_service_client().table("contacts").delete().eq("id", contact_id).execute()


def test_criar_e_listar_contato(client, gestor_token, test_tenant, gestor_user_id):
    created = _create_contact(client, gestor_token, gestor_user_id)
    try:
        assert created["journey_status"] == "lead"
        assert created["tenant_id"] == test_tenant["id"]

        listing = client.get("/api/v1/contacts", headers=auth_headers(gestor_token))
        assert any(c["id"] == created["id"] for c in listing.json())
    finally:
        _delete_contact(created["id"])


def test_criar_contato_forca_journey_status_lead(client, gestor_token, gestor_user_id):
    # ContactCreate nem expõe o campo journey_status (o Pydantic ignora o
    # campo extra), e o service também força "lead" no payload de insert —
    # garantimos aqui que mandar o campo no corpo não muda o resultado,
    # batendo com a regra do frontend de todo contato novo nascer "lead".
    created = _create_contact(client, gestor_token, gestor_user_id, journey_status="cliente")
    try:
        assert created["journey_status"] == "lead"
    finally:
        _delete_contact(created["id"])


def test_atendente_tem_acesso_completo_a_contacts(client, atendente_token, atendente_user_id):
    # Access model do módulo (ver brief): atendente e gestor têm acesso igual
    # a Contacts, sem require_role em nenhum endpoint. O brief só exercitava
    # os endpoints com gestor_token — este teste cobre a mesma jornada
    # (criar/ler/atualizar/listar) só com atendente_token para não deixar essa
    # premissa sem cobertura.
    created = _create_contact(client, atendente_token, atendente_user_id, name="Cliente do Atendente")
    try:
        get_response = client.get(f"/api/v1/contacts/{created['id']}", headers=auth_headers(atendente_token))
        assert get_response.status_code == 200

        update_response = client.patch(
            f"/api/v1/contacts/{created['id']}",
            json={"name": "Renomeado pelo Atendente"},
            headers=auth_headers(atendente_token),
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Renomeado pelo Atendente"

        listing = client.get("/api/v1/contacts", headers=auth_headers(atendente_token))
        assert listing.status_code == 200
        assert any(c["id"] == created["id"] for c in listing.json())
    finally:
        _delete_contact(created["id"])


def test_filtro_por_journey_status(client, gestor_token, gestor_user_id):
    created = _create_contact(client, gestor_token, gestor_user_id, name="Outro Cliente")
    try:
        response = client.get("/api/v1/contacts?journey_status=lead", headers=auth_headers(gestor_token))
        assert response.status_code == 200
        assert all(c["journey_status"] == "lead" for c in response.json())
        assert any(c["id"] == created["id"] for c in response.json())
    finally:
        _delete_contact(created["id"])


def test_filtros_por_origin_owner_tag_e_search(client, gestor_token, gestor_user_id, atendente_user_id):
    alvo = _create_contact(
        client,
        gestor_token,
        gestor_user_id,
        name="Fulano Pesquisavel",
        whatsapp="+5511977778888",
        origin="indicacao",
        tags=["vip"],
    )
    outro = _create_contact(
        client,
        gestor_token,
        atendente_user_id,
        name="Beltrano",
        whatsapp="+5511900001111",
        origin="instagram_ads",
        tags=["frio"],
    )
    try:
        by_origin = client.get("/api/v1/contacts?origin=indicacao", headers=auth_headers(gestor_token)).json()
        assert any(c["id"] == alvo["id"] for c in by_origin)
        assert all(c["origin"] == "indicacao" for c in by_origin)

        by_owner = client.get(
            f"/api/v1/contacts?owner_id={atendente_user_id}", headers=auth_headers(gestor_token)
        ).json()
        assert any(c["id"] == outro["id"] for c in by_owner)
        assert all(c["owner_id"] == atendente_user_id for c in by_owner)

        by_tag = client.get("/api/v1/contacts?tag=vip", headers=auth_headers(gestor_token)).json()
        assert any(c["id"] == alvo["id"] for c in by_tag)
        assert all("vip" in c["tags"] for c in by_tag)

        by_search_name = client.get("/api/v1/contacts?search=Pesquisavel", headers=auth_headers(gestor_token)).json()
        assert any(c["id"] == alvo["id"] for c in by_search_name)

        by_search_whatsapp = client.get(
            "/api/v1/contacts?search=977778888", headers=auth_headers(gestor_token)
        ).json()
        assert any(c["id"] == alvo["id"] for c in by_search_whatsapp)
    finally:
        _delete_contact(alvo["id"])
        _delete_contact(outro["id"])


def test_criar_contato_rejeita_owner_id_de_outro_tenant(client, gestor_token):
    # Important #2 do whole-branch review: create_contact gravava owner_id
    # sem checar tenant. Cria um gestor real em OUTRO tenant e usa seu id
    # como owner_id — espera 404 e nenhum contato vazando para o banco.
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Contacts Create", "slug": f"alheia-cc-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            response = client.post(
                "/api/v1/contacts",
                json={
                    "name": "Contato Owner Alheio", "whatsapp": "+5511900004444",
                    "origin": "outro", "owner_id": foreign_user_id,
                },
                headers=auth_headers(gestor_token),
            )
            assert response.status_code == 404

            leaked = sb.table("contacts").select("id").eq("whatsapp", "+5511900004444").execute().data
            assert leaked == []
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_atualizar_contato_rejeita_owner_id_de_outro_tenant(client, gestor_token, gestor_user_id):
    # Mesmo Important #2, mas via PATCH: update_contact não checava owner_id
    # quando presente no patch. Cria um contato próprio e tenta reatribuí-lo
    # a um owner_id de outro tenant — espera 404 e owner_id inalterado.
    created = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511900005555")
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Contacts Update", "slug": f"alheia-cu-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            response = client.patch(
                f"/api/v1/contacts/{created['id']}",
                json={"owner_id": foreign_user_id},
                headers=auth_headers(gestor_token),
            )
            assert response.status_code == 404

            unchanged = sb.table("contacts").select("owner_id").eq("id", created["id"]).execute().data[0]
            assert unchanged["owner_id"] == gestor_user_id
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
        _delete_contact(created["id"])


def test_criar_e_atualizar_contato_grava_audit_log(client, gestor_token, gestor_user_id, test_tenant):
    created = _create_contact(client, gestor_token, gestor_user_id)
    try:
        sb = get_service_client()
        insert_logs = (
            sb.table("audit_log")
            .select("*")
            .eq("table_name", "contacts")
            .eq("record_id", created["id"])
            .eq("action", "INSERT")
            .execute()
            .data
        )
        assert len(insert_logs) == 1
        assert insert_logs[0]["user_id"] == gestor_user_id
        assert insert_logs[0]["tenant_id"] == test_tenant["id"]

        client.patch(f"/api/v1/contacts/{created['id']}", json={"name": "Novo Nome"}, headers=auth_headers(gestor_token))
        update_logs = (
            sb.table("audit_log")
            .select("*")
            .eq("table_name", "contacts")
            .eq("record_id", created["id"])
            .eq("action", "UPDATE")
            .execute()
            .data
        )
        assert len(update_logs) == 1
        assert update_logs[0]["user_id"] == gestor_user_id
    finally:
        _delete_contact(created["id"])


def test_atualizar_contato_inexistente_404(client, gestor_token):
    response = client.patch(
        "/api/v1/contacts/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 404


def test_buscar_contato_inexistente_404(client, gestor_token):
    response = client.get(
        "/api/v1/contacts/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 404


def test_gestor_exclui_contato_cascateia_tudo(client, gestor_token, gestor_user_id):
    """deals/appointments/activities/conversations/attachments têm contact_id
    NOT NULL — diferente de excluir deal (que só desvincula, ver
    test_deals.py), excluir um contato precisa apagar de verdade tudo que só
    existe por causa dele."""
    sb = get_service_client()
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511966665555")

    deal = client.post(
        "/api/v1/deals",
        json={
            "contact_id": contact["id"], "title": "Negócio Teste", "products": "iPhone 15",
            "value": 5000, "payment": "pix", "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    ).json()
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "contact_id": contact["id"], "deal_id": deal["id"], "type": "atendimento",
            "starts_at": "2026-09-01T10:00:00Z", "ends_at": "2026-09-01T10:30:00Z", "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    ).json()
    activity = sb.table("activities").insert(
        {
            "tenant_id": contact["tenant_id"], "contact_id": contact["id"], "deal_id": deal["id"],
            "user_id": gestor_user_id, "type": "mensagem", "description": "Nota de teste",
        }
    ).execute().data[0]
    conversation = client.post(
        "/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)
    ).json()
    message = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", json={"text": "Oi"}, headers=auth_headers(gestor_token)
    ).json()
    attachment = client.post(
        f"/api/v1/contacts/{contact['id']}/attachments",
        files={"file": ("comprovante.png", b"fake-bytes", "image/png")},
        headers=auth_headers(gestor_token),
    ).json()

    response = client.delete(f"/api/v1/contacts/{contact['id']}", headers=auth_headers(gestor_token))
    assert response.status_code == 200

    assert sb.table("contacts").select("id").eq("id", contact["id"]).execute().data == []
    assert sb.table("deals").select("id").eq("id", deal["id"]).execute().data == []
    assert sb.table("appointments").select("id").eq("id", appointment["id"]).execute().data == []
    assert sb.table("activities").select("id").eq("id", activity["id"]).execute().data == []
    assert sb.table("conversations").select("id").eq("id", conversation["id"]).execute().data == []
    assert sb.table("messages").select("id").eq("id", message["id"]).execute().data == []
    assert sb.table("attachments").select("id").eq("id", attachment["id"]).execute().data == []


def test_gestor_ve_contagem_de_exclusao_do_contato(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511966664444")
    try:
        deal = client.post(
            "/api/v1/deals",
            json={
                "contact_id": contact["id"], "title": "Negócio", "products": "iPad",
                "value": 3000, "payment": "pix", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        ).json()
        try:
            summary = client.get(
                f"/api/v1/contacts/{contact['id']}/deletion-summary", headers=auth_headers(gestor_token)
            )
            assert summary.status_code == 200
            body = summary.json()
            assert body["deals"] == 1
            assert body["appointments"] == 0
            assert body["activities"] == 0
            assert body["attachments"] == 0
        finally:
            get_service_client().table("deals").delete().eq("id", deal["id"]).execute()
    finally:
        _delete_contact(contact["id"])


def test_atendente_nao_exclui_contato(client, atendente_token, atendente_user_id):
    contact = _create_contact(client, atendente_token, atendente_user_id, whatsapp="+5511966663333")
    try:
        response = client.delete(f"/api/v1/contacts/{contact['id']}", headers=auth_headers(atendente_token))
        assert response.status_code == 403
    finally:
        _delete_contact(contact["id"])


def test_excluir_contato_inexistente_404(client, gestor_token):
    response = client.delete(
        "/api/v1/contacts/00000000-0000-0000-0000-000000000000", headers=auth_headers(gestor_token)
    )
    assert response.status_code == 404


def test_nao_exclui_contato_de_outro_tenant(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Contacts Delete", "slug": f"alheia-cd-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Alheio",
                        "whatsapp": "+5511900008888", "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                response = client.delete(
                    f"/api/v1/contacts/{foreign_contact['id']}", headers=auth_headers(gestor_token)
                )
                assert response.status_code == 404

                survives = sb.table("contacts").select("id").eq("id", foreign_contact["id"]).execute().data
                assert len(survives) == 1
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_admin_impersonando_cria_contato_como_proprio_responsavel(client, admin_token, admin_user_id, test_tenant):
    """Mesma exceção de deals (verify_owner_or_self): admin_saas não tem linha
    em user_profiles vinculada a este tenant, mas pode se atribuir contatos
    como responsável enquanto está impersonando a loja."""
    headers = {**auth_headers(admin_token), "X-Impersonate-Tenant": test_tenant["id"]}
    response = client.post(
        "/api/v1/contacts",
        json={"name": "Cliente Admin", "whatsapp": "+5511999990099", "origin": "whatsapp_direto", "owner_id": admin_user_id},
        headers=headers,
    )
    try:
        assert response.status_code == 200
        assert response.json()["owner_id"] == admin_user_id
    finally:
        if response.status_code == 200:
            _delete_contact(response.json()["id"])
