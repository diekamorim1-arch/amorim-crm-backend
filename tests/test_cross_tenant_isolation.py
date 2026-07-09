"""Verificação final (Task 12): prova de isolamento entre tenants com um
SEGUNDO tenant/gestor completamente independente do `test_tenant` principal
(que já é compartilhado por toda a suíte). Complementa — não substitui — os
testes de "não referenciar recurso de outro tenant na criação" já cobertos
nas Tasks 6-10 (deals/suppliers/appointments/connections): aqui o foco é
"o que um usuário de OUTRO tenant enxerga/alcança", via listagem e acesso
direto por id.
"""

import uuid

import pytest

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


@pytest.fixture(scope="module")
def other_tenant():
    sb = get_service_client()
    tenant = sb.table("tenants").insert(
        {"name": "Outra Loja", "slug": f"outra-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    yield tenant
    # Mesma ordem de limpeza de `test_tenant` em conftest.py: user_profiles
    # antes de tenants (FK), como salvaguarda caso `_other_gestor` não tenha
    # limpado por algum motivo.
    sb.table("user_profiles").delete().eq("tenant_id", tenant["id"]).execute()
    sb.table("tenants").delete().eq("id", tenant["id"]).execute()


@pytest.fixture(scope="module")
def _other_gestor(other_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, other_tenant["id"], "gestor")
    yield token, user_id
    sb.table("user_profiles").delete().eq("id", user_id).execute()
    sb.auth.admin.delete_user(user_id)


@pytest.fixture(scope="module")
def other_gestor_token(_other_gestor) -> str:
    return _other_gestor[0]


def test_contatos_nao_vazam_entre_tenants(client, gestor_token, other_gestor_token, gestor_user_id):
    created = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Isolado", "whatsapp": "+5511700000000", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    try:
        from_other_tenant = client.get("/api/v1/contacts", headers=auth_headers(other_gestor_token))
        assert all(c["id"] != created["id"] for c in from_other_tenant.json())

        direct_get = client.get(f"/api/v1/contacts/{created['id']}", headers=auth_headers(other_gestor_token))
        assert direct_get.status_code == 404
    finally:
        get_service_client().table("contacts").delete().eq("id", created["id"]).execute()


def test_dashboard_nao_mistura_dados_de_outro_tenant(client, gestor_token, other_gestor_token):
    own = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()
    other = client.get("/api/v1/dashboard/metrics", headers=auth_headers(other_gestor_token)).json()
    # other_tenant acabou de ser criado neste módulo e não tem nenhum deal, logo
    # suas métricas devem refletir exatamente zero — provando que o cálculo do
    # gestor do other_tenant não está agregando nada do test_tenant (que, sendo
    # session-scoped e compartilhado, quase certamente tem dados != zero).
    assert other["new_leads_month"] == 0
    assert other["revenue_month"] == 0
    assert other["in_negotiation_value"] == 0
    assert own != other or (own["new_leads_month"] == 0 and other["new_leads_month"] == 0)


def test_fornecedores_nao_vazam_entre_tenants(client, gestor_token, other_gestor_token, test_tenant):
    sb = get_service_client()
    supplier = (
        sb.table("suppliers")
        .insert({"tenant_id": test_tenant["id"], "name": "Fornecedor Isolado", "whatsapp": "+5511700000001"})
        .execute()
        .data[0]
    )
    try:
        listing = client.get("/api/v1/suppliers", headers=auth_headers(other_gestor_token))
        assert listing.status_code == 200
        assert all(s["id"] != supplier["id"] for s in listing.json())

        direct_get = client.get(f"/api/v1/suppliers/{supplier['id']}", headers=auth_headers(other_gestor_token))
        assert direct_get.status_code == 404

        # confirma, por contraste, que o próprio tenant continua enxergando o
        # fornecedor normalmente (isolamento não é um bug de leitura geral).
        own_get = client.get(f"/api/v1/suppliers/{supplier['id']}", headers=auth_headers(gestor_token))
        assert own_get.status_code == 200
    finally:
        sb.table("suppliers").delete().eq("id", supplier["id"]).execute()


def test_deals_nao_vazam_entre_tenants(client, other_gestor_token, gestor_user_id, test_tenant):
    sb = get_service_client()
    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Contato Deal Isolado", "whatsapp": "+5511700000002",
                "origin": "outro", "owner_id": gestor_user_id,
            }
        )
        .execute()
        .data[0]
    )
    deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "owner_id": gestor_user_id,
                "title": "Negocio Isolado", "products": "iPhone", "value": 1000, "payment": "pix",
                "stage": "novo_lead",
            }
        )
        .execute()
        .data[0]
    )
    try:
        listing = client.get("/api/v1/deals", headers=auth_headers(other_gestor_token))
        assert listing.status_code == 200
        assert all(d["id"] != deal["id"] for d in listing.json())

        # não há GET /deals/{id}; o equivalente de "acesso direto" é qualquer
        # endpoint que opera sobre um deal_id específico (move/mark-lost) —
        # deve ser 404 para quem não pertence ao tenant, nunca vazar/alterar.
        move_attempt = client.post(
            f"/api/v1/deals/{deal['id']}/move", json={"stage": "em_atendimento"}, headers=auth_headers(other_gestor_token)
        )
        assert move_attempt.status_code == 404

        unchanged = sb.table("deals").select("stage").eq("id", deal["id"]).execute().data[0]
        assert unchanged["stage"] == "novo_lead"
    finally:
        sb.table("deals").delete().eq("id", deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_conexoes_nao_vazam_entre_tenants(client, other_gestor_token, gestor_user_id, test_tenant):
    sb = get_service_client()
    connection = (
        sb.table("connections")
        .insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511700000003"})
        .execute()
        .data[0]
    )
    try:
        listing = client.get("/api/v1/connections", headers=auth_headers(other_gestor_token))
        assert listing.status_code == 200
        assert all(c["id"] != connection["id"] for c in listing.json())

        pair_attempt = client.post(
            f"/api/v1/connections/{connection['id']}/pair", headers=auth_headers(other_gestor_token)
        )
        assert pair_attempt.status_code == 404

        unchanged = sb.table("connections").select("status").eq("id", connection["id"]).execute().data[0]
        assert unchanged["status"] == "desconectado"
    finally:
        sb.table("connections").delete().eq("id", connection["id"]).execute()
