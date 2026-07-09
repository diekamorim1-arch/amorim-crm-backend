import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import auth_headers


def _create_supplier(client, token, **overrides):
    payload = {"name": "Fornecedor Teste", "whatsapp": "+5511944440000"}
    payload.update(overrides)
    response = client.post("/api/v1/suppliers", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _create_product(client, token, supplier_id, **overrides):
    payload = {"name": "iPhone Teste", "current_price": 3000}
    payload.update(overrides)
    response = client.post(f"/api/v1/suppliers/{supplier_id}/products", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _cleanup_supplier(*supplier_ids: str) -> None:
    # FK-safe: supplier_price_changes -> supplier_products -> suppliers.
    sb = get_service_client()
    for supplier_id in supplier_ids:
        products = sb.table("supplier_products").select("id").eq("supplier_id", supplier_id).execute().data
        for product in products:
            sb.table("supplier_price_changes").delete().eq("supplier_product_id", product["id"]).execute()
        sb.table("supplier_products").delete().eq("supplier_id", supplier_id).execute()
        sb.table("suppliers").delete().eq("id", supplier_id).execute()


def test_gestor_cria_fornecedor_produto_e_historico_de_preco_fica_correto(client, gestor_token):
    supplier = _create_supplier(client, gestor_token, whatsapp="+5511944441111")
    try:
        product = _create_product(client, gestor_token, supplier["id"], current_price=3000)
        assert product["current_price"] == 3000
        assert product["supplier_id"] == supplier["id"]

        # create_product não deve gerar uma linha de histórico: o histórico só
        # nasce quando o preço é de fato alterado depois.
        empty_history = client.get(
            f"/api/v1/supplier-products/{product['id']}/price-history", headers=auth_headers(gestor_token)
        )
        assert empty_history.status_code == 200
        assert empty_history.json() == []

        first_update = client.patch(
            f"/api/v1/supplier-products/{product['id']}/price", json={"price": 3200}, headers=auth_headers(gestor_token)
        )
        assert first_update.status_code == 200
        assert first_update.json()["current_price"] == 3200

        second_update = client.patch(
            f"/api/v1/supplier-products/{product['id']}/price", json={"price": 3500}, headers=auth_headers(gestor_token)
        )
        assert second_update.status_code == 200
        assert second_update.json()["current_price"] == 3500

        # duas mudanças de preço reais devem gerar duas linhas de histórico
        # distintas (nenhuma sobrescrita), ordenadas da mais nova pra mais
        # antiga.
        history = client.get(
            f"/api/v1/supplier-products/{product['id']}/price-history", headers=auth_headers(gestor_token)
        ).json()
        assert len(history) == 2
        assert history[0]["price"] == 3500
        assert history[1]["price"] == 3200
        assert history[0]["changed_at"] >= history[1]["changed_at"]

        # o preço corrente e o "products" refletem só a última mudança.
        products = client.get(f"/api/v1/suppliers/{supplier['id']}/products", headers=auth_headers(gestor_token)).json()
        assert any(p["id"] == product["id"] and p["current_price"] == 3500 for p in products)
    finally:
        _cleanup_supplier(supplier["id"])


def test_gestor_atualiza_fornecedor_com_patch_parcial(client, gestor_token):
    supplier = _create_supplier(
        client, gestor_token, whatsapp="+5511944442222", contact_name="Joao", email="joao@fornecedor.com"
    )
    try:
        updated = client.patch(
            f"/api/v1/suppliers/{supplier['id']}", json={"name": "Fornecedor Renomeado"}, headers=auth_headers(gestor_token)
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["name"] == "Fornecedor Renomeado"
        # campos não enviados no patch permanecem intactos.
        assert body["contact_name"] == "Joao"
        assert body["email"] == "joao@fornecedor.com"

        empty_patch = client.patch(f"/api/v1/suppliers/{supplier['id']}", json={}, headers=auth_headers(gestor_token))
        assert empty_patch.status_code == 400
    finally:
        _cleanup_supplier(supplier["id"])


def test_atendente_le_todos_os_endpoints_de_leitura(client, atendente_token, gestor_token):
    supplier = _create_supplier(client, gestor_token, whatsapp="+5511944443333")
    try:
        product = _create_product(client, gestor_token, supplier["id"])
        client.patch(
            f"/api/v1/supplier-products/{product['id']}/price", json={"price": 3300}, headers=auth_headers(gestor_token)
        )

        list_resp = client.get("/api/v1/suppliers", headers=auth_headers(atendente_token))
        assert list_resp.status_code == 200
        assert any(s["id"] == supplier["id"] for s in list_resp.json())

        get_resp = client.get(f"/api/v1/suppliers/{supplier['id']}", headers=auth_headers(atendente_token))
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == supplier["id"]

        products_resp = client.get(f"/api/v1/suppliers/{supplier['id']}/products", headers=auth_headers(atendente_token))
        assert products_resp.status_code == 200
        assert any(p["id"] == product["id"] for p in products_resp.json())

        history_resp = client.get(
            f"/api/v1/supplier-products/{product['id']}/price-history", headers=auth_headers(atendente_token)
        )
        assert history_resp.status_code == 200
        assert len(history_resp.json()) == 1
        assert history_resp.json()[0]["price"] == 3300

        # o mesmo gestor que criou também deve conseguir ler tudo, provando
        # que a leitura não é exclusiva de um papel.
        assert client.get("/api/v1/suppliers", headers=auth_headers(gestor_token)).status_code == 200
        assert client.get(f"/api/v1/suppliers/{supplier['id']}", headers=auth_headers(gestor_token)).status_code == 200
    finally:
        _cleanup_supplier(supplier["id"])


def test_atendente_recebe_403_em_todos_os_endpoints_de_escrita(client, atendente_token, gestor_token):
    supplier = _create_supplier(client, gestor_token, whatsapp="+5511944444444")
    try:
        product = _create_product(client, gestor_token, supplier["id"])

        create_supplier_resp = client.post(
            "/api/v1/suppliers", json={"name": "Nao Deveria", "whatsapp": "+5511944445555"}, headers=auth_headers(atendente_token)
        )
        assert create_supplier_resp.status_code == 403

        update_supplier_resp = client.patch(
            f"/api/v1/suppliers/{supplier['id']}", json={"name": "Nao Deveria"}, headers=auth_headers(atendente_token)
        )
        assert update_supplier_resp.status_code == 403

        create_product_resp = client.post(
            f"/api/v1/suppliers/{supplier['id']}/products",
            json={"name": "Nao Deveria", "current_price": 100},
            headers=auth_headers(atendente_token),
        )
        assert create_product_resp.status_code == 403

        update_price_resp = client.patch(
            f"/api/v1/supplier-products/{product['id']}/price", json={"price": 999}, headers=auth_headers(atendente_token)
        )
        assert update_price_resp.status_code == 403

        # nenhuma das tentativas negadas deve ter deixado rastro: preço e
        # histórico continuam como estavam antes.
        history = client.get(
            f"/api/v1/supplier-products/{product['id']}/price-history", headers=auth_headers(gestor_token)
        ).json()
        assert history == []
    finally:
        _cleanup_supplier(supplier["id"])


def test_fornecedor_inexistente_retorna_404(client, gestor_token):
    fake_id = "00000000-0000-0000-0000-000000000000"
    get_resp = client.get(f"/api/v1/suppliers/{fake_id}", headers=auth_headers(gestor_token))
    assert get_resp.status_code == 404

    update_resp = client.patch(f"/api/v1/suppliers/{fake_id}", json={"name": "X"}, headers=auth_headers(gestor_token))
    assert update_resp.status_code == 404


def test_produto_inexistente_retorna_404_ao_atualizar_preco(client, gestor_token):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.patch(f"/api/v1/supplier-products/{fake_id}/price", json={"price": 100}, headers=auth_headers(gestor_token))
    assert resp.status_code == 404


def test_nao_cria_produto_referenciando_fornecedor_de_outro_tenant(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert({"name": "Loja Alheia", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}).execute().data[0]
    try:
        foreign_supplier = (
            sb.table("suppliers")
            .insert({"tenant_id": foreign_tenant["id"], "name": "Fornecedor Alheio", "whatsapp": "+5511900000000"})
            .execute()
            .data[0]
        )
        try:
            # gestor do test_tenant tenta criar um produto referenciando um
            # supplier_id que pertence a OUTRO tenant: precisa ser bloqueado
            # com 404, nunca inserir a linha cross-tenant silenciosamente.
            response = client.post(
                f"/api/v1/suppliers/{foreign_supplier['id']}/products",
                json={"name": "Produto Indevido", "current_price": 100},
                headers=auth_headers(gestor_token),
            )
            assert response.status_code == 404

            leaked = sb.table("supplier_products").select("id").eq("supplier_id", foreign_supplier["id"]).execute().data
            assert leaked == []
        finally:
            sb.table("suppliers").delete().eq("id", foreign_supplier["id"]).execute()
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()


def test_busca_por_nome_filtra_fornecedores(client, gestor_token):
    supplier_a = _create_supplier(client, gestor_token, name="Distribuidora Alpha", whatsapp="+5511944446666")
    supplier_b = _create_supplier(client, gestor_token, name="Distribuidora Beta", whatsapp="+5511944447777")
    try:
        resp = client.get("/api/v1/suppliers", params={"search": "Alpha"}, headers=auth_headers(gestor_token))
        assert resp.status_code == 200
        names = [s["name"] for s in resp.json()]
        assert "Distribuidora Alpha" in names
        assert "Distribuidora Beta" not in names
    finally:
        _cleanup_supplier(supplier_a["id"], supplier_b["id"])
