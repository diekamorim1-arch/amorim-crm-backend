from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_suppliers(tenant_id: str, search: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("suppliers").select("*").eq("tenant_id", tenant_id)
    if search:
        query = query.ilike("name", f"%{search}%")
    return query.execute().data


def get_supplier(tenant_id: str, supplier_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("suppliers").select("*").eq("tenant_id", tenant_id).eq("id", supplier_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Fornecedor não encontrado.")
    return rows[0]


def create_supplier(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    return sb.table("suppliers").insert({**data, "tenant_id": tenant_id}).execute().data[0]


def update_supplier(tenant_id: str, supplier_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    rows = sb.table("suppliers").update(clean_patch).eq("tenant_id", tenant_id).eq("id", supplier_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Fornecedor não encontrado.")
    return rows[0]


def list_products(tenant_id: str, supplier_id: str) -> list[dict]:
    sb = get_service_client()
    return sb.table("supplier_products").select("*").eq("tenant_id", tenant_id).eq("supplier_id", supplier_id).execute().data


def create_product(tenant_id: str, supplier_id: str, name: str, current_price: float) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    return (
        sb.table("supplier_products")
        .insert({"tenant_id": tenant_id, "supplier_id": supplier_id, "name": name, "current_price": current_price, "updated_at": now})
        .execute()
        .data[0]
    )


def update_price(tenant_id: str, product_id: str, price: float) -> dict:
    sb = get_service_client()
    rows = sb.table("supplier_products").select("id").eq("tenant_id", tenant_id).eq("id", product_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Produto não encontrado.")
    now = datetime.now(UTC).isoformat()
    sb.table("supplier_price_changes").insert(
        {"tenant_id": tenant_id, "supplier_product_id": product_id, "price": price, "changed_at": now}
    ).execute()
    return (
        sb.table("supplier_products")
        .update({"current_price": price, "updated_at": now})
        .eq("id", product_id)
        .execute()
        .data[0]
    )


def price_history(tenant_id: str, product_id: str) -> list[dict]:
    sb = get_service_client()
    return (
        sb.table("supplier_price_changes")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("supplier_product_id", product_id)
        .order("changed_at", desc=True)
        .execute()
        .data
    )
