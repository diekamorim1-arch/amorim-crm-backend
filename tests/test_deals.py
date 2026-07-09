import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _create_lead(client, token, owner_id, **overrides):
    payload = {
        "name": "Lead Teste", "whatsapp": "+5511988880000", "origin": "instagram_organico",
        "value": 5000, "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/leads", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _cleanup_lead(*contact_ids: str) -> None:
    # create_lead (compound) grava contact + deal + activity numa "transação
    # lógica" — activities.deal_id e activities.contact_id, além de
    # deals.contact_id, são FKs sem cascade (ver schema), então a ordem de
    # limpeza importa: activities antes de deals antes de contacts.
    sb = get_service_client()
    for contact_id in contact_ids:
        sb.table("activities").delete().eq("contact_id", contact_id).execute()
        sb.table("deals").delete().eq("contact_id", contact_id).execute()
        sb.table("contacts").delete().eq("id", contact_id).execute()


def _create_contact(client, token, owner_id, **overrides):
    payload = {
        "name": "Cliente Deal Teste", "whatsapp": "+5511911110000", "origin": "whatsapp_direto",
        "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def test_criar_lead_gera_contato_e_deal(client, gestor_token, gestor_user_id):
    deal = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511988880001")
    try:
        assert deal["stage"] == "novo_lead"
        assert deal["outcome"] == "aberto"
        assert deal["owner_id"] == gestor_user_id

        # o contato de fato existe e nasceu como "lead", batendo com a regra
        # do reducer do frontend para todo lead novo.
        contact = get_service_client().table("contacts").select("*").eq("id", deal["contact_id"]).execute().data[0]
        assert contact["journey_status"] == "lead"
        assert contact["owner_id"] == gestor_user_id

        # a activity de "novo lead criado" também foi gravada.
        activities = get_service_client().table("activities").select("*").eq("deal_id", deal["id"]).execute().data
        assert len(activities) == 1
        assert activities[0]["type"] == "mudanca_estagio"
    finally:
        _cleanup_lead(deal["contact_id"])


def test_mover_deal_para_pos_venda_marca_ganho_e_journey_status_cliente(client, gestor_token, gestor_user_id):
    deal = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511977770000")
    try:
        moved = client.post(f"/api/v1/deals/{deal['id']}/move", json={"stage": "pos_venda"}, headers=auth_headers(gestor_token))
        assert moved.status_code == 200
        body = moved.json()
        assert body["stage"] == "pos_venda"
        assert body["outcome"] == "ganho"

        contact = get_service_client().table("contacts").select("*").eq("id", deal["contact_id"]).execute().data[0]
        assert contact["journey_status"] == "cliente"

        # duas activities: a de "novo lead" (da criação) + a de mudança de
        # estágio; e mais uma de "venda", já que é uma vitória.
        activities = get_service_client().table("activities").select("*").eq("deal_id", deal["id"]).execute().data
        assert len(activities) == 3
        assert any(a["type"] == "venda" for a in activities)
    finally:
        _cleanup_lead(deal["contact_id"])


def test_segunda_venda_do_mesmo_contato_marca_journey_status_recorrente(client, gestor_token, gestor_user_id):
    # Primeiro negócio do contato: vitória -> "cliente".
    primeiro = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511977771111")
    try:
        move1 = client.post(
            f"/api/v1/deals/{primeiro['id']}/move", json={"stage": "pos_venda"}, headers=auth_headers(gestor_token)
        )
        assert move1.status_code == 200

        # Segundo negócio criado direto para o MESMO contato (não via /leads,
        # que sempre cria um contato novo) e também vencido -> "recorrente".
        segundo_response = client.post(
            "/api/v1/deals",
            json={
                "contact_id": primeiro["contact_id"], "title": "Segunda compra", "products": "iPad",
                "value": 4000, "payment": "pix", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        )
        assert segundo_response.status_code == 200
        segundo = segundo_response.json()

        move2 = client.post(
            f"/api/v1/deals/{segundo['id']}/move", json={"stage": "pos_venda"}, headers=auth_headers(gestor_token)
        )
        assert move2.status_code == 200
        assert move2.json()["outcome"] == "ganho"

        contact = get_service_client().table("contacts").select("*").eq("id", primeiro["contact_id"]).execute().data[0]
        assert contact["journey_status"] == "recorrente"

        get_service_client().table("activities").delete().eq("deal_id", segundo["id"]).execute()
        get_service_client().table("deals").delete().eq("id", segundo["id"]).execute()
    finally:
        _cleanup_lead(primeiro["contact_id"])


def test_mover_para_mesmo_estagio_e_no_op(client, gestor_token, gestor_user_id):
    deal = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511966660000")
    try:
        before_activities = get_service_client().table("activities").select("*").eq("deal_id", deal["id"]).execute().data
        assert len(before_activities) == 1

        moved = client.post(f"/api/v1/deals/{deal['id']}/move", json={"stage": "novo_lead"}, headers=auth_headers(gestor_token))
        assert moved.status_code == 200
        assert moved.json()["stage_changed_at"] == deal["stage_changed_at"]

        after_activities = get_service_client().table("activities").select("*").eq("deal_id", deal["id"]).execute().data
        assert len(after_activities) == len(before_activities)
    finally:
        _cleanup_lead(deal["contact_id"])


def test_marcar_perdido_exige_motivo_e_seta_outcome(client, gestor_token, gestor_user_id):
    deal = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511955551111")
    try:
        sem_motivo = client.post(f"/api/v1/deals/{deal['id']}/mark-lost", json={}, headers=auth_headers(gestor_token))
        assert sem_motivo.status_code == 422

        com_motivo = client.post(
            f"/api/v1/deals/{deal['id']}/mark-lost", json={"reason": "preco"}, headers=auth_headers(gestor_token)
        )
        assert com_motivo.status_code == 200
        body = com_motivo.json()
        assert body["outcome"] == "perdido"
        assert body["loss_reason"] == "preco"
    finally:
        _cleanup_lead(deal["contact_id"])


def test_atendente_nao_edita_financeiro_mas_gestor_pode(client, atendente_token, gestor_token, gestor_user_id):
    deal = _create_lead(client, gestor_token, gestor_user_id, whatsapp="+5511955550000")
    try:
        negado = client.patch(
            f"/api/v1/deals/{deal['id']}/financials",
            json={"supplier_value": 3000, "gift_value": 100},
            headers=auth_headers(atendente_token),
        )
        assert negado.status_code == 403

        permitido = client.patch(
            f"/api/v1/deals/{deal['id']}/financials",
            json={"supplier_value": 3000, "gift_value": 100},
            headers=auth_headers(gestor_token),
        )
        assert permitido.status_code == 200
        body = permitido.json()
        assert body["supplier_value"] == 3000
        assert body["gift_value"] == 100
    finally:
        _cleanup_lead(deal["contact_id"])


def test_atendente_tem_acesso_completo_ao_pipeline(client, atendente_token, atendente_user_id):
    # Access model do módulo (ver brief): atendente e gestor têm acesso igual
    # a todo o pipeline, exceto financials (gestor-only, coberto acima).
    deal = _create_lead(client, atendente_token, atendente_user_id, whatsapp="+5511944440000")
    try:
        listing = client.get("/api/v1/deals", headers=auth_headers(atendente_token))
        assert listing.status_code == 200
        assert any(d["id"] == deal["id"] for d in listing.json())

        moved = client.post(f"/api/v1/deals/{deal['id']}/move", json={"stage": "em_atendimento"}, headers=auth_headers(atendente_token))
        assert moved.status_code == 200
        assert moved.json()["stage"] == "em_atendimento"

        lost = client.post(f"/api/v1/deals/{deal['id']}/mark-lost", json={"reason": "sem_resposta"}, headers=auth_headers(atendente_token))
        assert lost.status_code == 200
        assert lost.json()["outcome"] == "perdido"
    finally:
        _cleanup_lead(deal["contact_id"])


def test_criar_deal_para_contato_existente_e_atualizar(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp="+5511933330000")
    try:
        created = client.post(
            "/api/v1/deals",
            json={
                "contact_id": contact["id"], "title": "iPhone 15", "products": "iPhone 15 Pro",
                "value": 7000, "payment": "cartao_parcelado", "owner_id": gestor_user_id,
            },
            headers=auth_headers(gestor_token),
        )
        assert created.status_code == 200
        deal = created.json()
        assert deal["stage"] == "novo_lead"
        assert deal["outcome"] == "aberto"

        updated = client.patch(f"/api/v1/deals/{deal['id']}", json={"value": 6500}, headers=auth_headers(gestor_token))
        assert updated.status_code == 200
        assert updated.json()["value"] == 6500

        get_service_client().table("deals").delete().eq("id", deal["id"]).execute()
    finally:
        get_service_client().table("contacts").delete().eq("id", contact["id"]).execute()


def test_mover_deal_inexistente_404(client, gestor_token):
    response = client.post(
        "/api/v1/deals/00000000-0000-0000-0000-000000000000/move",
        json={"stage": "novo_lead"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 404


def test_nao_cria_lead_ou_deal_referenciando_recursos_de_outro_tenant(client, gestor_token, gestor_user_id):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert({"name": "Loja Alheia", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Cliente Alheio", "whatsapp": "+5511900001111",
                        "origin": "whatsapp_direto", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                # 1) /leads com owner_id de OUTRO tenant: create_lead precisa
                # validar que o responsável pertence ao tenant do chamador
                # antes de criar contact/deal referenciando esse id.
                lead_response = client.post(
                    "/api/v1/leads",
                    json={
                        "name": "Lead Indevido", "whatsapp": "+5511900002222", "origin": "instagram_organico",
                        "value": 1000, "owner_id": foreign_user_id,
                    },
                    headers=auth_headers(gestor_token),
                )
                assert lead_response.status_code == 404

                leaked_contacts = (
                    sb.table("contacts").select("id").eq("whatsapp", "+5511900002222").execute().data
                )
                assert leaked_contacts == []

                # 2) /deals com contact_id de OUTRO tenant (owner_id válido no
                # próprio tenant): create_deal precisa validar contact_id
                # antes de inserir a linha cross-tenant.
                deal_response = client.post(
                    "/api/v1/deals",
                    json={
                        "contact_id": foreign_contact["id"], "title": "Negócio Indevido", "products": "iPhone",
                        "value": 2000, "payment": "pix", "owner_id": gestor_user_id,
                    },
                    headers=auth_headers(gestor_token),
                )
                assert deal_response.status_code == 404

                leaked_deals = sb.table("deals").select("id").eq("contact_id", foreign_contact["id"]).execute().data
                assert leaked_deals == []
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
