import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _cleanup(*expense_ids: str) -> None:
    sb = get_service_client()
    for expense_id in expense_ids:
        sb.table("expenses").delete().eq("id", expense_id).execute()


def test_gestor_cria_e_lista_gasto(client, gestor_token, gestor_user_id, test_tenant):
    created = client.post(
        "/api/v1/expenses",
        json={"description": "Caixas de embalagem", "value": 45.9},
        headers=auth_headers(gestor_token),
    )
    try:
        assert created.status_code == 200
        body = created.json()
        assert body["description"] == "Caixas de embalagem"
        assert body["value"] == 45.9
        assert body["tenant_id"] == test_tenant["id"]
        assert body["user_id"] == gestor_user_id

        listing = client.get("/api/v1/expenses", headers=auth_headers(gestor_token))
        assert listing.status_code == 200
        assert any(e["id"] == body["id"] for e in listing.json())
    finally:
        _cleanup(created.json()["id"] if created.status_code == 200 else "")


def test_atendente_nao_cria_gasto_mas_pode_listar(client, atendente_token):
    negado = client.post(
        "/api/v1/expenses", json={"description": "Não deveria", "value": 10}, headers=auth_headers(atendente_token)
    )
    assert negado.status_code == 403

    listagem = client.get("/api/v1/expenses", headers=auth_headers(atendente_token))
    assert listagem.status_code == 200


def test_gestor_exclui_gasto(client, gestor_token):
    created = client.post(
        "/api/v1/expenses", json={"description": "Gasto a excluir", "value": 20}, headers=auth_headers(gestor_token)
    ).json()

    deleted = client.delete(f"/api/v1/expenses/{created['id']}", headers=auth_headers(gestor_token))
    assert deleted.status_code == 200

    listing = client.get("/api/v1/expenses", headers=auth_headers(gestor_token))
    assert all(e["id"] != created["id"] for e in listing.json())


def test_atendente_nao_exclui_gasto(client, atendente_token, gestor_token):
    created = client.post(
        "/api/v1/expenses", json={"description": "Gasto protegido", "value": 30}, headers=auth_headers(gestor_token)
    ).json()
    try:
        response = client.delete(f"/api/v1/expenses/{created['id']}", headers=auth_headers(atendente_token))
        assert response.status_code == 403
    finally:
        _cleanup(created["id"])


def test_excluir_gasto_inexistente_404(client, gestor_token):
    response = client.delete(
        "/api/v1/expenses/00000000-0000-0000-0000-000000000000", headers=auth_headers(gestor_token)
    )
    assert response.status_code == 404


def test_gasto_de_outro_tenant_nao_e_visivel_nem_excluivel(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Gastos", "slug": f"alheia-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_expense = (
                sb.table("expenses")
                .insert({"tenant_id": foreign_tenant["id"], "description": "Gasto alheio", "value": 15, "user_id": foreign_user_id})
                .execute()
                .data[0]
            )
            try:
                listing = client.get("/api/v1/expenses", headers=auth_headers(gestor_token))
                assert all(e["id"] != foreign_expense["id"] for e in listing.json())

                delete_response = client.delete(
                    f"/api/v1/expenses/{foreign_expense['id']}", headers=auth_headers(gestor_token)
                )
                assert delete_response.status_code == 404
                assert sb.table("expenses").select("id").eq("id", foreign_expense["id"]).execute().data != []
            finally:
                sb.table("expenses").delete().eq("id", foreign_expense["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
