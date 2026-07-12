from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant


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


def create_product(tenant_id: str, supplier_id: str, name: str, current_price: float, colors: str | None = None) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("suppliers", supplier_id, tenant_id, "Fornecedor não encontrado.")
    now = datetime.now(UTC).isoformat()
    return (
        sb.table("supplier_products")
        .insert(
            {
                "tenant_id": tenant_id, "supplier_id": supplier_id, "name": name, "current_price": current_price,
                "colors": colors, "updated_at": now,
            }
        )
        .execute()
        .data[0]
    )


def bulk_create_products(tenant_id: str, supplier_id: str, items: list[dict]) -> list[dict]:
    sb = get_service_client()
    verify_owned_by_tenant("suppliers", supplier_id, tenant_id, "Fornecedor não encontrado.")
    if not items:
        return []
    now = datetime.now(UTC).isoformat()
    rows = [
        {
            "tenant_id": tenant_id, "supplier_id": supplier_id, "name": item["name"],
            "current_price": item["current_price"], "colors": item.get("colors"), "updated_at": now,
        }
        for item in items
    ]
    return sb.table("supplier_products").insert(rows).execute().data


def update_product(tenant_id: str, product_id: str, name: str | None, price: float | None, colors: str | None = None) -> dict:
    sb = get_service_client()
    rows = sb.table("supplier_products").select("*").eq("tenant_id", tenant_id).eq("id", product_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Produto não encontrado.")
    product = rows[0]
    now = datetime.now(UTC).isoformat()
    patch: dict = {}
    if name is not None:
        patch["name"] = name
    if colors is not None:
        patch["colors"] = colors
    # Mesma regra do reducer local que este endpoint substitui: só grava uma
    # entrada em supplier_price_changes quando o preço realmente muda, não a
    # cada edição do produto (ex.: editar só o nome não deveria poluir o
    # histórico de preço com uma entrada idêntica à anterior).
    price_changed = price is not None and price != product["current_price"]
    if price_changed:
        patch["current_price"] = price
        patch["updated_at"] = now
        sb.table("supplier_price_changes").insert(
            {"tenant_id": tenant_id, "supplier_product_id": product_id, "price": price, "changed_at": now}
        ).execute()
    if not patch:
        return product
    return sb.table("supplier_products").update(patch).eq("id", product_id).execute().data[0]


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
