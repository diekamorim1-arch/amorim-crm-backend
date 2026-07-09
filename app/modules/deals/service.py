from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant

PRODUCT_LINE_LABELS = {
    "iphone": "iPhone", "ipad": "iPad", "mac": "Mac", "watch": "Apple Watch",
    "airpods": "AirPods", "acessorios": "Acessórios",
}


def list_deals(tenant_id: str, stage: str | None, outcome: str | None, owner_id: str | None, contact_id: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("deals").select("*").eq("tenant_id", tenant_id)
    if stage:
        query = query.eq("stage", stage)
    if outcome:
        query = query.eq("outcome", outcome)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if contact_id:
        query = query.eq("contact_id", contact_id)
    return query.execute().data


def create_lead(tenant_id: str, name: str, whatsapp: str, origin: str, product_line: str | None, value: float, owner_id: str) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", owner_id, tenant_id, "Responsável não encontrado.")
    now = datetime.now(UTC).isoformat()
    product_label = PRODUCT_LINE_LABELS.get(product_line, "Novo negócio")

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": tenant_id, "name": name, "whatsapp": whatsapp, "origin": origin,
                "interests": [product_line] if product_line else [], "journey_status": "lead",
                "owner_id": owner_id, "first_contact_at": now, "last_interaction_at": now,
            }
        )
        .execute()
        .data[0]
    )
    deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": tenant_id, "contact_id": contact["id"], "title": product_label, "products": product_label,
                "value": value, "payment": "pix", "stage": "novo_lead", "outcome": "aberto",
                "owner_id": owner_id, "stage_changed_at": now,
            }
        )
        .execute()
        .data[0]
    )
    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": contact["id"], "deal_id": deal["id"], "user_id": owner_id,
            "type": "mudanca_estagio", "description": f"Novo lead criado: {product_label}.",
        }
    ).execute()
    return deal


def create_deal(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("contacts", data["contact_id"], tenant_id, "Cliente não encontrado.")
    verify_owned_by_tenant("user_profiles", data["owner_id"], tenant_id, "Responsável não encontrado.")
    now = datetime.now(UTC).isoformat()
    payload = {**data, "tenant_id": tenant_id, "stage": "novo_lead", "outcome": "aberto", "stage_changed_at": now}
    return sb.table("deals").insert(payload).execute().data[0]


def _get_deal(sb, tenant_id: str, deal_id: str) -> dict:
    rows = sb.table("deals").select("*").eq("tenant_id", tenant_id).eq("id", deal_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Negócio não encontrado.")
    return rows[0]


def update_deal(tenant_id: str, deal_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    _get_deal(sb, tenant_id, deal_id)
    return sb.table("deals").update(clean_patch).eq("id", deal_id).execute().data[0]


def move_deal(tenant_id: str, deal_id: str, stage: str, user_id: str) -> dict:
    sb = get_service_client()
    deal = _get_deal(sb, tenant_id, deal_id)
    if deal["stage"] == stage:
        return deal  # no-op, mesma guarda do reducer do frontend

    now = datetime.now(UTC).isoformat()
    is_win = stage == "pos_venda"
    patch = {"stage": stage, "stage_changed_at": now}
    if is_win:
        patch["outcome"] = "ganho"
    updated = sb.table("deals").update(patch).eq("id", deal_id).execute().data[0]

    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": deal["contact_id"], "deal_id": deal_id, "user_id": user_id,
            "type": "mudanca_estagio", "description": f"Deal movido para o estágio {stage}.",
        }
    ).execute()

    if is_win:
        sb.table("activities").insert(
            {
                "tenant_id": tenant_id, "contact_id": deal["contact_id"], "deal_id": deal_id, "user_id": user_id,
                "type": "venda", "description": f"Venda concluída: {deal['products']}.",
            }
        ).execute()
        won_count = (
            sb.table("deals")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("contact_id", deal["contact_id"])
            .eq("outcome", "ganho")
            .execute()
            .count
        )
        journey_status = "recorrente" if won_count >= 2 else "cliente"
        sb.table("contacts").update({"journey_status": journey_status}).eq("id", deal["contact_id"]).execute()

    return updated


def mark_lost(tenant_id: str, deal_id: str, reason: str) -> dict:
    sb = get_service_client()
    _get_deal(sb, tenant_id, deal_id)
    return sb.table("deals").update({"outcome": "perdido", "loss_reason": reason}).eq("id", deal_id).execute().data[0]


def update_financials(tenant_id: str, deal_id: str, supplier_product_id: str | None, supplier_value: float, gift_value: float) -> dict:
    sb = get_service_client()
    _get_deal(sb, tenant_id, deal_id)
    patch = {"supplier_product_id": supplier_product_id, "supplier_value": supplier_value, "gift_value": gift_value}
    return sb.table("deals").update(patch).eq("id", deal_id).execute().data[0]
