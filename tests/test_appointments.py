import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _create_contact(client, token, owner_id, **overrides):
    payload = {
        "name": "Contato Agenda",
        "whatsapp": "+5511800000000",
        "origin": "outro",
        "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _cleanup(contact_ids: list[str] | None = None, appointment_ids: list[str] | None = None) -> None:
    sb = get_service_client()
    for appointment_id in appointment_ids or []:
        sb.table("appointments").delete().eq("id", appointment_id).execute()
    for contact_id in contact_ids or []:
        sb.table("contacts").delete().eq("id", contact_id).execute()


def test_criar_listar_e_concluir_agendamento(client, gestor_token, gestor_user_id):
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Agenda", "whatsapp": "+5511800000000", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    try:
        created = client.post(
            "/api/v1/appointments",
            json={
                "contact_id": contact["id"], "type": "entrega", "starts_at": "2026-08-01T10:00:00Z",
                "ends_at": "2026-08-01T10:30:00Z", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        )
        assert created.status_code == 200
        appointment_id = created.json()["id"]

        listing = client.get(
            "/api/v1/appointments?from=2026-08-01T00:00:00Z&to=2026-08-01T23:59:59Z", headers=auth_headers(gestor_token)
        )
        assert any(a["id"] == appointment_id for a in listing.json())

        concluded = client.patch(
            f"/api/v1/appointments/{appointment_id}", json={"status": "concluido"}, headers=auth_headers(gestor_token)
        )
        assert concluded.json()["status"] == "concluido"
    finally:
        _cleanup(contact_ids=[contact["id"]], appointment_ids=[created.json()["id"]] if created.status_code == 200 else [])


def test_atendente_tem_acesso_completo_a_appointments(client, atendente_token, atendente_user_id):
    # Access model do módulo (ver brief): atendente e gestor têm acesso igual a
    # appointments, sem require_role em nenhum endpoint. Cobrindo a mesma
    # jornada (criar/listar/atualizar) só com atendente_token.
    contact = _create_contact(client, atendente_token, atendente_user_id, whatsapp="+5511800000001")
    appointment_id = None
    try:
        created = client.post(
            "/api/v1/appointments",
            json={
                "contact_id": contact["id"], "type": "atendimento", "starts_at": "2026-08-02T09:00:00Z",
                "ends_at": "2026-08-02T09:30:00Z", "owner_id": atendente_user_id,
            },
            headers=auth_headers(atendente_token),
        )
        assert created.status_code == 200
        appointment_id = created.json()["id"]

        listing = client.get("/api/v1/appointments", headers=auth_headers(atendente_token))
        assert listing.status_code == 200
        assert any(a["id"] == appointment_id for a in listing.json())

        updated = client.patch(
            f"/api/v1/appointments/{appointment_id}", json={"note": "Confirmado"}, headers=auth_headers(atendente_token)
        )
        assert updated.status_code == 200
        assert updated.json()["note"] == "Confirmado"
    finally:
        _cleanup(contact_ids=[contact["id"]], appointment_ids=[appointment_id] if appointment_id else [])


def test_filtro_por_intervalo_de_datas_exclui_agendamento_fora_do_range(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511800000002")
    dentro_id = None
    fora_id = None
    try:
        dentro = client.post(
            "/api/v1/appointments",
            json={
                "contact_id": contact["id"], "type": "follow_up", "starts_at": "2026-09-10T10:00:00Z",
                "ends_at": "2026-09-10T10:30:00Z", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        )
        assert dentro.status_code == 200
        dentro_id = dentro.json()["id"]

        fora = client.post(
            "/api/v1/appointments",
            json={
                "contact_id": contact["id"], "type": "follow_up", "starts_at": "2026-09-20T10:00:00Z",
                "ends_at": "2026-09-20T10:30:00Z", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        )
        assert fora.status_code == 200
        fora_id = fora.json()["id"]

        listing = client.get(
            "/api/v1/appointments?from=2026-09-09T00:00:00Z&to=2026-09-11T00:00:00Z", headers=auth_headers(gestor_token)
        )
        assert listing.status_code == 200
        ids = [a["id"] for a in listing.json()]
        assert dentro_id in ids
        assert fora_id not in ids
    finally:
        _cleanup(contact_ids=[contact["id"]], appointment_ids=[i for i in (dentro_id, fora_id) if i])


def test_atualizar_agendamento_inexistente_404(client, gestor_token):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.patch(f"/api/v1/appointments/{fake_id}", json={"status": "concluido"}, headers=auth_headers(gestor_token))
    assert response.status_code == 404


def test_nao_cria_agendamento_referenciando_contato_de_outro_tenant(client, gestor_token, gestor_user_id):
    """Guarda de tenant (mesma classe de vulnerabilidade corrigida nas Tasks
    6/7/8): contact_id de um tenant diferente não pode ser usado para criar um
    agendamento no tenant do chamador."""
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Estrangeiro", "whatsapp": "+5511988880000",
                        "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                response = client.post(
                    "/api/v1/appointments",
                    json={
                        "contact_id": foreign_contact["id"], "type": "atendimento", "starts_at": "2026-08-03T10:00:00Z",
                        "ends_at": "2026-08-03T10:30:00Z", "owner_id": gestor_user_id,
                    },
                    headers=auth_headers(gestor_token),
                )
                assert response.status_code == 404

                leaked = sb.table("appointments").select("id").eq("contact_id", foreign_contact["id"]).execute().data
                assert leaked == []
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_nao_cria_agendamento_referenciando_deal_de_outro_tenant(client, gestor_token, gestor_user_id):
    """Mesma guarda de tenant, agora para deal_id (opcional): um negócio de
    outro tenant não pode ser referenciado num agendamento do tenant do
    chamador."""
    sb = get_service_client()
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511800000003")
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Deals", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Estrangeiro Deal", "whatsapp": "+5511988881111",
                        "origin": "outro", "owner_id": foreign_user_id,
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
                            "owner_id": foreign_user_id, "title": "Negocio Estrangeiro", "products": "iPhone",
                            "value": 100, "payment": "pix", "stage": "novo_lead",
                        }
                    )
                    .execute()
                    .data[0]
                )
                try:
                    response = client.post(
                        "/api/v1/appointments",
                        json={
                            "contact_id": contact["id"], "deal_id": foreign_deal["id"], "type": "atendimento",
                            "starts_at": "2026-08-04T10:00:00Z", "ends_at": "2026-08-04T10:30:00Z", "owner_id": gestor_user_id,
                        },
                        headers=auth_headers(gestor_token),
                    )
                    assert response.status_code == 404

                    leaked = sb.table("appointments").select("id").eq("deal_id", foreign_deal["id"]).execute().data
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


def test_admin_impersonando_cria_agendamento_como_proprio_responsavel(
    client, admin_token, admin_user_id, gestor_token, gestor_user_id, test_tenant
):
    """Mesma exceção de deals/contacts (verify_owner_or_self) — cobre o
    router de appointments, que antes desta leva nem sequer injetava
    AuthContext (só tenant_id), então is_impersonating precisou ser
    adicionado do zero aqui."""
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Admin", "whatsapp": "+5511800000099", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()
    try:
        headers = {**auth_headers(admin_token), "X-Impersonate-Tenant": test_tenant["id"]}
        created = client.post(
            "/api/v1/appointments",
            json={
                "contact_id": contact["id"], "type": "entrega", "starts_at": "2026-08-05T10:00:00Z",
                "ends_at": "2026-08-05T10:30:00Z", "owner_id": admin_user_id,
            },
            headers=headers,
        )
        assert created.status_code == 200
        assert created.json()["owner_id"] == admin_user_id
    finally:
        _cleanup(
            contact_ids=[contact["id"]],
            appointment_ids=[created.json()["id"]] if created.status_code == 200 else [],
        )
