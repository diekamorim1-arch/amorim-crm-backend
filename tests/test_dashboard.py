from datetime import UTC, datetime

import pytest

from app.core.supabase_client import get_service_client
from tests.conftest import auth_headers


def test_atendente_nao_acessa_dashboard(client, atendente_token):
    response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(atendente_token))
    assert response.status_code == 403


def test_gestor_recebe_metricas_com_todas_as_chaves(client, gestor_token):
    response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    body = response.json()
    for key in (
        "new_leads_month", "in_negotiation_value", "revenue_month", "revenue_prev_month",
        "conversion_rate", "net_profit_month", "funnel_counts", "by_channel", "loss_ranking",
    ):
        assert key in body


def _channel_won(body: dict, origin: str) -> int:
    for entry in body["by_channel"]:
        if entry["origin"] == origin:
            return entry["won"]
    return 0


def test_metricas_batem_com_calculo_manual(client, gestor_token, gestor_user_id, test_tenant):
    # test_tenant é session-scoped e compartilhado entre TODOS os arquivos de
    # teste da suíte, então não assumimos que deals/contacts do tenant estão
    # vazios aqui — capturamos o estado "antes" (via chamada real ao endpoint,
    # e via consulta direta para os contadores won/perdido que a fórmula de
    # conversion_rate usa) e conferimos que o delta introduzido pelos dados
    # QUE ESTE TESTE cria bate com o cálculo manual esperado.
    sb = get_service_client()

    before_response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token))
    assert before_response.status_code == 200
    before = before_response.json()

    baseline_deals = sb.table("deals").select("outcome").eq("tenant_id", test_tenant["id"]).execute().data
    baseline_won = sum(1 for d in baseline_deals if d["outcome"] == "ganho")
    baseline_lost = sum(1 for d in baseline_deals if d["outcome"] == "perdido")

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Contato Dashboard Teste", "whatsapp": "+5511999990000",
                "origin": "instagram_organico", "owner_id": gestor_user_id,
            }
        )
        .execute()
        .data[0]
    )

    now = datetime.now(UTC).isoformat()

    # Dois deals GANHOS no MESMO contato: se by_channel.won contasse deals em
    # vez de contatos distintos, o "won" desse canal subiria em 2 em vez de 1
    # (era exatamente esse bug no seletor original do frontend).
    won_deal_1 = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Venda 1",
                "products": "Produto A", "value": 1000, "payment": "pix", "stage": "pos_venda",
                "outcome": "ganho", "owner_id": gestor_user_id, "stage_changed_at": now,
                "supplier_value": 300, "gift_value": 50,
            }
        )
        .execute()
        .data[0]
    )
    won_deal_2 = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Venda 2",
                "products": "Produto B", "value": 500, "payment": "pix", "stage": "pos_venda",
                "outcome": "ganho", "owner_id": gestor_user_id, "stage_changed_at": now,
                "supplier_value": 100, "gift_value": 0,
            }
        )
        .execute()
        .data[0]
    )
    lost_deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Negocio Perdido",
                "products": "Produto C", "value": 200, "payment": "pix", "stage": "negociacao",
                "outcome": "perdido", "loss_reason": "preco", "owner_id": gestor_user_id, "stage_changed_at": now,
            }
        )
        .execute()
        .data[0]
    )

    try:
        response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token))
        assert response.status_code == 200
        after = response.json()

        # revenue_month: soma de "value" dos deals GANHOS com stage_changed_at
        # no mes corrente. Nossos dois deals (1000 + 500 = 1500) foram
        # marcados ganhos AGORA, logo devem entrar integralmente no delta.
        expected_revenue_delta = 1000 + 500
        assert after["revenue_month"] == pytest.approx(before["revenue_month"] + expected_revenue_delta, abs=0.01)

        # net_profit_month: value - (supplier_value ou 0) - (gift_value ou 0),
        # somado só sobre os GANHOS do mês.
        # deal 1: 1000 - 300 - 50 = 650 | deal 2: 500 - 100 - 0 = 400
        expected_profit_delta = (1000 - 300 - 50) + (500 - 100 - 0)
        assert after["net_profit_month"] == pytest.approx(before["net_profit_month"] + expected_profit_delta, abs=0.01)

        # conversion_rate: won / (won + perdido) * 100, arredondado a 1 casa,
        # contabilizado sobre TODOS os deals do tenant (sem filtro de mês).
        # Criamos +2 ganhos e +1 perdido sobre a contagem baseline.
        expected_won = baseline_won + 2
        expected_lost = baseline_lost + 1
        expected_decided = expected_won + expected_lost
        expected_rate = round((expected_won / expected_decided) * 1000) / 10
        assert after["conversion_rate"] == expected_rate

        # by_channel.won: contatos DISTINTOS com pelo menos um deal ganho por
        # origem — não a contagem total de deals ganhos. O contato de teste
        # tem 2 deals ganhos mas é UM contato só, então o "won" do canal
        # instagram_organico deve subir em exatamente 1, não 2.
        before_channel_won = _channel_won(before, "instagram_organico")
        after_channel_won = _channel_won(after, "instagram_organico")
        assert after_channel_won == before_channel_won + 1
    finally:
        sb.table("deals").delete().eq("id", won_deal_1["id"]).execute()
        sb.table("deals").delete().eq("id", won_deal_2["id"]).execute()
        sb.table("deals").delete().eq("id", lost_deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_net_profit_month_subtrai_freight_value(client, gestor_token, gestor_user_id, test_tenant):
    # Bug encontrado na revisão de continuidade: net_profit_month somava
    # value - supplier_value - gift_value mas esquecia freight_value, mesmo
    # esse campo já existindo no Deal desde a Leva 1.1 (custo de frete).
    sb = get_service_client()
    before = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Contato Frete Teste", "whatsapp": "+5511999991111",
                "origin": "outro", "owner_id": gestor_user_id,
            }
        )
        .execute()
        .data[0]
    )
    now = datetime.now(UTC).isoformat()
    deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Venda com Frete",
                "products": "Produto Frete", "value": 1000, "payment": "pix", "stage": "pos_venda",
                "outcome": "ganho", "owner_id": gestor_user_id, "stage_changed_at": now,
                "supplier_value": 300, "gift_value": 50, "freight_value": 40,
            }
        )
        .execute()
        .data[0]
    )
    try:
        after = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()
        expected_delta = 1000 - 300 - 50 - 40
        assert after["net_profit_month"] == pytest.approx(before["net_profit_month"] + expected_delta, abs=0.01)
    finally:
        sb.table("deals").delete().eq("id", deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_monthly_history_tem_o_mes_atual_com_dados_esperados(client, gestor_token, gestor_user_id, test_tenant):
    sb = get_service_client()
    now = datetime.now(UTC)

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Contato Historico Teste", "whatsapp": "+5511999992222",
                "origin": "outro", "owner_id": gestor_user_id, "first_contact_at": now.isoformat(),
            }
        )
        .execute()
        .data[0]
    )
    deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Venda Historico",
                "products": "Produto Historico", "value": 800, "payment": "pix", "stage": "pos_venda",
                "outcome": "ganho", "owner_id": gestor_user_id, "stage_changed_at": now.isoformat(),
                "supplier_value": 200, "gift_value": 0, "freight_value": 0,
            }
        )
        .execute()
        .data[0]
    )
    try:
        response = client.get("/api/v1/dashboard/monthly-history?months=3", headers=auth_headers(gestor_token))
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3

        current_month_key = f"{now.year}-{now.month:02d}"
        current = next(item for item in body if item["month_key"] == current_month_key)
        assert current["new_leads"] >= 1
        assert current["revenue"] >= 800
        assert current["net_profit"] >= 600
    finally:
        sb.table("deals").delete().eq("id", deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_monthly_detail_lista_negocio_ganho_do_mes_com_nome_do_cliente(
    client, gestor_token, gestor_user_id, test_tenant
):
    sb = get_service_client()
    now = datetime.now(UTC)

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": test_tenant["id"], "name": "Cliente Detalhe Mensal", "whatsapp": "+5511999993333",
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
                "tenant_id": test_tenant["id"], "contact_id": contact["id"], "title": "Venda Detalhe",
                "products": "Produto Detalhe", "value": 1200, "payment": "cartao_avista", "stage": "pos_venda",
                "outcome": "ganho", "owner_id": gestor_user_id, "stage_changed_at": now.isoformat(),
                "supplier_value": 500, "gift_value": 20, "freight_value": 30,
            }
        )
        .execute()
        .data[0]
    )
    try:
        response = client.get(
            f"/api/v1/dashboard/monthly-history/{now.year}/{now.month}", headers=auth_headers(gestor_token)
        )
        assert response.status_code == 200
        rows = response.json()
        row = next(r for r in rows if r["deal_id"] == deal["id"])
        assert row["contact_name"] == "Cliente Detalhe Mensal"
        assert row["net_profit"] == pytest.approx(1200 - 500 - 20 - 30, abs=0.01)
    finally:
        sb.table("deals").delete().eq("id", deal["id"]).execute()
        sb.table("contacts").delete().eq("id", contact["id"]).execute()


def test_atendente_nao_acessa_monthly_history(client, atendente_token):
    response = client.get("/api/v1/dashboard/monthly-history", headers=auth_headers(atendente_token))
    assert response.status_code == 403
