import uuid

from app.core.audit import log_audit_event
from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant

BUCKET = "attachments"
# Mesmo teto de 1,5MB por arquivo já usado no frontend (Leva 1.2, ajustado
# após uma revisão de segurança sobre estouro de cota) — mantido aqui como a
# fonte de verdade agora que o arquivo passa a subir pro backend de verdade.
MAX_FILE_BYTES = 1_500_000
SIGNED_URL_TTL_SECONDS = 300


def _with_signed_url(sb, row: dict) -> dict:
    signed = sb.storage.from_(BUCKET).create_signed_url(row["storage_path"], SIGNED_URL_TTL_SECONDS)
    return {**row, "url": signed["signedURL"]}


def list_attachments(tenant_id: str, contact_id: str) -> list[dict]:
    sb = get_service_client()
    verify_owned_by_tenant("contacts", contact_id, tenant_id, "Cliente não encontrado.")
    rows = (
        sb.table("attachments")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("contact_id", contact_id)
        .order("uploaded_at", desc=True)
        .execute()
        .data
    )
    return [_with_signed_url(sb, row) for row in rows]


def create_attachment(
    tenant_id: str, user_id: str, contact_id: str, file_name: str, file_type: str, content: bytes
) -> dict:
    if len(content) > MAX_FILE_BYTES:
        raise AppError(413, "file_too_large", "Arquivo maior que 1,5MB.")
    sb = get_service_client()
    verify_owned_by_tenant("contacts", contact_id, tenant_id, "Cliente não encontrado.")

    storage_path = f"{tenant_id}/{uuid.uuid4()}-{file_name}"
    sb.storage.from_(BUCKET).upload(storage_path, content, {"content-type": file_type})

    row = (
        sb.table("attachments")
        .insert(
            {
                "tenant_id": tenant_id,
                "contact_id": contact_id,
                "file_name": file_name,
                "file_type": file_type,
                "storage_path": storage_path,
                "uploaded_by": user_id,
            }
        )
        .execute()
        .data[0]
    )
    log_audit_event(tenant_id, user_id, "INSERT", "attachments", row["id"])
    return _with_signed_url(sb, row)


def delete_attachment(tenant_id: str, user_id: str, attachment_id: str) -> None:
    sb = get_service_client()
    rows = sb.table("attachments").select("*").eq("tenant_id", tenant_id).eq("id", attachment_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Comprovante não encontrado.")
    row = rows[0]
    sb.storage.from_(BUCKET).remove([row["storage_path"]])
    sb.table("attachments").delete().eq("id", attachment_id).execute()
    log_audit_event(tenant_id, user_id, "DELETE", "attachments", attachment_id)
