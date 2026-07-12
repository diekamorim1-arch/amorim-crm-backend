from fastapi import BackgroundTasks

from app.core.audit import log_audit_event
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_expenses(tenant_id: str) -> list[dict]:
    sb = get_service_client()
    return sb.table("expenses").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).execute().data


def create_expense(tenant_id: str, user_id: str, description: str, value: float, background_tasks: BackgroundTasks) -> dict:
    sb = get_service_client()
    expense = (
        sb.table("expenses")
        .insert({"tenant_id": tenant_id, "description": description, "value": value, "user_id": user_id})
        .execute()
        .data[0]
    )
    background_tasks.add_task(log_audit_event, tenant_id, user_id, "INSERT", "expenses", expense["id"])
    return expense


def delete_expense(tenant_id: str, actor_user_id: str, expense_id: str, background_tasks: BackgroundTasks) -> None:
    sb = get_service_client()
    existing = sb.table("expenses").select("id").eq("tenant_id", tenant_id).eq("id", expense_id).execute().data
    if not existing:
        raise AppError(404, "not_found", "Gasto não encontrado.")
    sb.table("expenses").delete().eq("tenant_id", tenant_id).eq("id", expense_id).execute()
    background_tasks.add_task(log_audit_event, tenant_id, actor_user_id, "DELETE", "expenses", expense_id)
