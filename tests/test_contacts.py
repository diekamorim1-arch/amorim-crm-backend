from app.core.supabase_client import get_service_client
from tests.conftest import auth_headers


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
