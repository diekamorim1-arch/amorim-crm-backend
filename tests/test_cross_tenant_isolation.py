"""Verificação final (Task 12): prova de isolamento entre tenants com um
SEGUNDO tenant/gestor completamente independente do `test_tenant` principal
(que já é compartilhado por toda a suíte). Complementa — não substitui — os
testes de "não referenciar recurso de outro tenant na criação" já cobertos
nas Tasks 6-10 (deals/suppliers/appointments/connections): aqui o foco é
"o que um usuário de OUTRO tenant enxerga/alcança", via listagem e acesso
direto por id.
"""

import uuid
from datetime import UTC, datetime

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


def test_dashboard_nao_mistura_dados_de_outro_tenant(client, gestor_token, other_gestor_token, gestor_user_id, test_tenant):
    # test_tenant é session-scoped e compartilhado por toda a suíte, e todo
    # outro arquivo de teste limpa seus próprios dados em `finally` — então,
    # dependendo da ordem de coleta do pytest, test_tenant pode estar
    # zerado no momento em que este teste roda. Se comparássemos "own" (vazio)
    # com "other" (vazio, tenant recém-criado), o teste passaria mesmo se o
    # dashboard não filtrasse por tenant_id — dois estados vazios são
    # indistinguíveis de "isolado". Por isso injetamos dado real e não-zero em
    # test_tenant ANTES de comparar, e conferimos que:
    #   1) as métricas do PRÓPRIO test_tenant de fato mudaram (prova que o
    #      dado entrou no cálculo de alguém);
    #   2) as métricas do other_tenant continuam exatamente zero (prova que
    #      esse dado não vazou para o cálculo de outro tenant).
    sb = get_service_client()
    before = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()

    now = datetime.now(UTC).isoformat()
    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Contato Dashboard Isolamento", "whatsapp": "+5511700000004",
                "origin": "instagram_organico", "owner_id": gestor_user_id,
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
                "title": "Venda Isolamento Dashboard", "products": "iPhone", "value": 12345, "payment": "pix",
                "stage": "pos_venda", "outcome": "ganho", "stage_changed_at": now,
            }
        )
        .execute()
        .data[0]
    )
    try:
        own = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()
        other = client.get("/api/v1/dashboard/metrics", headers=auth_headers(other_gestor_token)).json()

        # 1) o deal ganho de 12345, com stage_changed_at agora, precisa ter
        # entrado no revenue_month do PRÓPRIO tenant — provando que os dados
        # inseridos realmente afetam algum cálculo (não é um teste vazio).
        assert own["revenue_month"] == pytest.approx(before["revenue_month"] + 12345, abs=0.01)
        assert own["new_leads_month"] >= before["new_leads_month"] + 1

        # 2) nada disso pode aparecer nas métricas do other_tenant: ele
        # acabou de ser criado neste módulo, sem nenhum contact/deal próprio,
        # então devem continuar exatamente zero mesmo com test_tenant agora
        # tendo dados reais e não-zero.
        assert other["new_leads_month"] == 0
        assert other["revenue_month"] == 0
        assert other["in_negotiation_value"] == 0
    finally:
        sb.table("deals").delete().eq("id", deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


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
