import time
import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _create_contact(client, token, owner_id, **overrides):
    payload = {
        "name": "Contato Timeline", "whatsapp": "+5511899990000", "origin": "outro", "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _cleanup(contact_ids: list[str] | None = None, activity_ids: list[str] | None = None) -> None:
    sb = get_service_client()
    for activity_id in activity_ids or []:
        sb.table("activities").delete().eq("id", activity_id).execute()
    for contact_id in contact_ids or []:
        sb.table("contacts").delete().eq("id", contact_id).execute()


def test_criar_e_listar_activity(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id)
    activity_id = None
    try:
        created = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Nota de teste."},
            headers=auth_headers(gestor_token),
        )
        assert created.status_code == 200
        activity_id = created.json()["id"]

        listing = client.get(f"/api/v1/activities?contact_id={contact['id']}", headers=auth_headers(gestor_token))
        assert len(listing.json()) == 1
    finally:
        _cleanup(contact_ids=[contact["id"]], activity_ids=[activity_id] if activity_id else [])


def test_listagem_ordena_por_criacao_desc(client, gestor_token, gestor_user_id):
    # Cobre `order("created_at", desc=True)` em list_activities: com duas
    # atividades criadas em sequência, a mais recente deve vir primeiro.
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511899990001")
    ids: list[str] = []
    try:
        primeira = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Primeira nota."},
            headers=auth_headers(gestor_token),
        )
        assert primeira.status_code == 200
        primeira_id = primeira.json()["id"]
        ids.append(primeira_id)
        time.sleep(0.01)

        segunda = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Segunda nota."},
            headers=auth_headers(gestor_token),
        )
        assert segunda.status_code == 200
        segunda_id = segunda.json()["id"]
        ids.append(segunda_id)

        listing = client.get(f"/api/v1/activities?contact_id={contact['id']}", headers=auth_headers(gestor_token))
        assert listing.status_code == 200
        body = listing.json()
        assert len(body) == 2
        assert body[0]["id"] == segunda_id
        assert body[1]["id"] == primeira_id
    finally:
        _cleanup(contact_ids=[contact["id"]], activity_ids=ids)


def test_atendente_tem_acesso_completo_a_activities(client, atendente_token, atendente_user_id):
    # Access model do módulo (ver brief): atendente e gestor têm acesso igual a
    # activities, sem require_role em nenhum endpoint.
    contact = _create_contact(client, atendente_token, atendente_user_id, whatsapp="+5511899990002")
    activity_id = None
    try:
        created = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Nota do atendente."},
            headers=auth_headers(atendente_token),
        )
        assert created.status_code == 200
        activity_id = created.json()["id"]

        listing = client.get(f"/api/v1/activities?contact_id={contact['id']}", headers=auth_headers(atendente_token))
        assert listing.status_code == 200
        assert any(a["id"] == activity_id for a in listing.json())
    finally:
        _cleanup(contact_ids=[contact["id"]], activity_ids=[activity_id] if activity_id else [])


def test_nao_cria_activity_referenciando_contato_de_outro_tenant(client, gestor_token):
    """Guarda de tenant (mesma classe de vulnerabilidade corrigida nas Tasks
    6/7/8/9): contact_id de um tenant diferente não pode ser usado para criar
    uma atividade no tenant do chamador."""
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Activities", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Estrangeiro Activity",
                        "whatsapp": "+5511988882222", "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                response = client.post(
                    "/api/v1/activities",
                    json={"contact_id": foreign_contact["id"], "type": "nota", "description": "Tentativa indevida."},
                    headers=auth_headers(gestor_token),
                )
                assert response.status_code == 404

                leaked = sb.table("activities").select("id").eq("contact_id", foreign_contact["id"]).execute().data
                assert leaked == []
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_lista_atividades_recentes_do_tenant_ordenadas(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511899990004")
    ids: list[str] = []
    try:
        primeira = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Nota recente 1."},
            headers=auth_headers(gestor_token),
        )
        ids.append(primeira.json()["id"])
        time.sleep(0.01)

        segunda = client.post(
            "/api/v1/activities",
            json={"contact_id": contact["id"], "type": "nota", "description": "Nota recente 2."},
            headers=auth_headers(gestor_token),
        )
        ids.append(segunda.json()["id"])

        response = client.get("/api/v1/activities/recent?limit=2", headers=auth_headers(gestor_token))
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["id"] == segunda.json()["id"]
    finally:
        _cleanup(contact_ids=[contact["id"]], activity_ids=ids)


def test_recent_respeita_o_limit(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511899990005")
    ids: list[str] = []
    try:
        for i in range(3):
            created = client.post(
                "/api/v1/activities",
                json={"contact_id": contact["id"], "type": "nota", "description": f"Nota {i}."},
                headers=auth_headers(gestor_token),
            )
            ids.append(created.json()["id"])

        response = client.get("/api/v1/activities/recent?limit=1", headers=auth_headers(gestor_token))
        assert response.status_code == 200
        assert len(response.json()) == 1
    finally:
        _cleanup(contact_ids=[contact["id"]], activity_ids=ids)


def test_admin_saas_sem_tenant_nao_acessa_recent(client):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, None, "admin_saas")
    try:
        response = client.get("/api/v1/activities/recent", headers=auth_headers(token))
        assert response.status_code == 400
    finally:
        sb.table("user_profiles").delete().eq("id", user_id).execute()
        sb.auth.admin.delete_user(user_id)


def test_nao_cria_activity_referenciando_deal_de_outro_tenant(client, gestor_token, gestor_user_id):
    """Mesma guarda de tenant, agora para deal_id (opcional): um negócio de
    outro tenant não pode ser referenciado numa atividade do tenant do
    chamador."""
    sb = get_service_client()
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511899990003")
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Activities Deal", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Estrangeiro Activity Deal",
                        "whatsapp": "+5511988883333", "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                foreign_deal = (
                    sb.table("deals")
                    .insert(
                        {
                            "tenant_id": foreign_tenant["id"], "contact_id": foreign_contact["id"],
                            "owner_id": foreign_user_id, "title": "Negocio Estrangeiro Activity", "products": "iPhone",
                            "value": 100, "payment": "pix", "stage": "novo_lead",
                        }
                    )
                    .execute()
                    .data[0]
                )
                try:
                    response = client.post(
                        "/api/v1/activities",
                        json={
                            "contact_id": contact["id"], "deal_id": foreign_deal["id"], "type": "nota",
                            "description": "Tentativa indevida com deal.",
                        },
                        headers=auth_headers(gestor_token),
                    )
                    assert response.status_code == 404

                    leaked = sb.table("activities").select("id").eq("deal_id", foreign_deal["id"]).execute().data
                    assert leaked == []
                finally:
                    sb.table("deals").delete().eq("id", foreign_deal["id"]).execute()
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
        _cleanup(contact_ids=[contact["id"]])
