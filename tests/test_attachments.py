import uuid

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


def _create_contact(client, token, owner_id, **overrides):
    payload = {
        "name": "Cliente Attachment Teste", "whatsapp": "+5511922220000", "origin": "whatsapp_direto",
        "owner_id": owner_id,
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload, headers=auth_headers(token))
    assert response.status_code == 200
    return response.json()


def _delete_contact(contact_id: str) -> None:
    get_service_client().table("contacts").delete().eq("id", contact_id).execute()


def test_upload_lista_e_deleta_anexo(client, gestor_token, gestor_user_id, test_tenant):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp=f"+5511{uuid.uuid4().int % 10**9}")
    try:
        upload = client.post(
            f"/api/v1/contacts/{contact['id']}/attachments",
            files={"file": ("comprovante.png", b"fake-png-bytes", "image/png")},
            headers=auth_headers(gestor_token),
        )
        assert upload.status_code == 200
        body = upload.json()
        assert body["contact_id"] == contact["id"]
        assert body["file_name"] == "comprovante.png"
        assert body["uploaded_by"] == gestor_user_id
        assert body["url"].startswith("http")

        listing = client.get(f"/api/v1/contacts/{contact['id']}/attachments", headers=auth_headers(gestor_token))
        assert listing.status_code == 200
        assert any(a["id"] == body["id"] for a in listing.json())

        deleted = client.delete(f"/api/v1/attachments/{body['id']}", headers=auth_headers(gestor_token))
        assert deleted.status_code == 200

        after_delete = client.get(f"/api/v1/contacts/{contact['id']}/attachments", headers=auth_headers(gestor_token))
        assert not any(a["id"] == body["id"] for a in after_delete.json())

        # Storage e linha do banco removidos de verdade, não só "escondidos".
        sb = get_service_client()
        assert sb.table("attachments").select("id").eq("id", body["id"]).execute().data == []
    finally:
        _delete_contact(contact["id"])


def test_upload_grava_audit_log(client, gestor_token, gestor_user_id, test_tenant):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp=f"+5511{uuid.uuid4().int % 10**9}")
    try:
        upload = client.post(
            f"/api/v1/contacts/{contact['id']}/attachments",
            files={"file": ("recibo.pdf", b"fake-pdf-bytes", "application/pdf")},
            headers=auth_headers(gestor_token),
        )
        attachment_id = upload.json()["id"]

        sb = get_service_client()
        insert_logs = (
            sb.table("audit_log")
            .select("*")
            .eq("table_name", "attachments")
            .eq("record_id", attachment_id)
            .eq("action", "INSERT")
            .execute()
            .data
        )
        assert len(insert_logs) == 1
        assert insert_logs[0]["user_id"] == gestor_user_id

        client.delete(f"/api/v1/attachments/{attachment_id}", headers=auth_headers(gestor_token))
        delete_logs = (
            sb.table("audit_log")
            .select("*")
            .eq("table_name", "attachments")
            .eq("record_id", attachment_id)
            .eq("action", "DELETE")
            .execute()
            .data
        )
        assert len(delete_logs) == 1
    finally:
        _delete_contact(contact["id"])


def test_upload_rejeita_arquivo_maior_que_1_5mb(client, gestor_token, gestor_user_id):
    contact = _create_contact(client, gestor_token, gestor_user_id, whatsapp=f"+5511{uuid.uuid4().int % 10**9}")
    try:
        big_content = b"x" * (1_500_001)
        response = client.post(
            f"/api/v1/contacts/{contact['id']}/attachments",
            files={"file": ("grande.png", big_content, "image/png")},
            headers=auth_headers(gestor_token),
        )
        assert response.status_code == 413

        sb = get_service_client()
        assert sb.table("attachments").select("id").eq("contact_id", contact["id"]).execute().data == []
    finally:
        _delete_contact(contact["id"])


def test_upload_rejeita_contact_id_de_outro_tenant(client, gestor_token):
    sb = get_service_client()
    foreign_tenant = sb.table("tenants").insert(
        {"name": "Loja Alheia Attachments", "slug": f"alheia-att-{uuid.uuid4().hex[:8]}"}
    ).execute().data[0]
    try:
        foreign_token, foreign_user_id = _create_user_and_sign_in(sb, foreign_tenant["id"], "gestor")
        try:
            foreign_contact = (
                sb.table("contacts")
                .insert(
                    {
                        "tenant_id": foreign_tenant["id"], "name": "Contato Alheio",
                        "whatsapp": "+5511900009999", "origin": "outro", "owner_id": foreign_user_id,
                    }
                )
                .execute()
                .data[0]
            )
            try:
                response = client.post(
                    f"/api/v1/contacts/{foreign_contact['id']}/attachments",
                    files={"file": ("x.png", b"conteudo", "image/png")},
                    headers=auth_headers(gestor_token),
                )
                assert response.status_code == 404

                assert sb.table("attachments").select("id").eq("contact_id", foreign_contact["id"]).execute().data == []
            finally:
                sb.table("contacts").delete().eq("id", foreign_contact["id"]).execute()
        finally:
            sb.table("user_profiles").delete().eq("id", foreign_user_id).execute()
            sb.auth.admin.delete_user(foreign_user_id)
    finally:
        sb.table("tenants").delete().eq("id", foreign_tenant["id"]).execute()
