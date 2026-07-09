import re
import unicodedata
import uuid

from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def list_tenants() -> list[dict]:
    sb = get_service_client()
    return sb.table("tenants").select("*").execute().data


def create_tenant(name: str, plan: str) -> dict:
    sb = get_service_client()
    tenant = sb.table("tenants").insert({"name": name, "slug": _slugify(name), "plan": plan}).execute().data[0]

    email = f"gestor.{uuid.uuid4().hex[:8]}@{tenant['slug']}.amorimcrm.com.br"
    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
            "app_metadata": {"tenant_id": tenant["id"], "role": "gestor"},
        }
    )
    sb.table("user_profiles").insert(
        {"id": created.user.id, "tenant_id": tenant["id"], "role": "gestor", "name": f"Gestor {name}"}
    ).execute()
    return tenant


def update_tenant(
    tenant_id: str,
    requester_tenant_id: str | None,
    requester_role: str,
    is_admin: bool,
    name: str | None,
    plan: str | None,
) -> dict:
    if not is_admin and (requester_role != "gestor" or requester_tenant_id != tenant_id):
        raise AppError(403, "forbidden", "Você só pode editar a própria loja.")
    if plan is not None and not is_admin:
        raise AppError(403, "forbidden", "Apenas o admin da plataforma pode alterar o plano da loja.")
    patch = {k: v for k, v in {"name": name, "plan": plan}.items() if v is not None}
    if not patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    sb = get_service_client()
    return sb.table("tenants").update(patch).eq("id", tenant_id).execute().data[0]


def update_tenant_settings(tenant_id: str, requester_tenant_id: str, patch: dict) -> dict:
    if requester_tenant_id != tenant_id:
        raise AppError(403, "forbidden", "Você só pode editar a própria loja.")
    sb = get_service_client()
    current = sb.table("tenants").select("settings").eq("id", tenant_id).execute().data
    if not current:
        raise AppError(404, "not_found", "Loja não encontrada.")
    merged = {**current[0]["settings"], **{k: v for k, v in patch.items() if v is not None}}
    return sb.table("tenants").update({"settings": merged}).eq("id", tenant_id).execute().data[0]


def check_tenant_for_impersonation(tenant_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("tenants").select("id, name").eq("id", tenant_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Loja não encontrada.")
    return rows[0]
