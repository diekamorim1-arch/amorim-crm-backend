from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def verify_owned_by_tenant(table: str, row_id: str, tenant_id: str, not_found_message: str) -> None:
    sb = get_service_client()
    rows = sb.table(table).select("id").eq("tenant_id", tenant_id).eq("id", row_id).execute().data
    if not rows:
        raise AppError(404, "not_found", not_found_message)
