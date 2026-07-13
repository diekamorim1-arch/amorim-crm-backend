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


def get_tenant(tenant_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("tenants").select("*").eq("id", tenant_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Loja não encontrada.")
    return rows[0]


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
    rows = sb.table("tenants").select("id, name, status").eq("id", tenant_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Loja não encontrada.")
    # Lojas suspensas não são bloqueadas aqui: suspender é uma ação do próprio
    # admin_saas, que precisa poder entrar na loja pra investigar/resolver o
    # que motivou a suspensão.
    return rows[0]


def get_tenant_deletion_summary(tenant_id: str) -> dict:
    sb = get_service_client()
    if not sb.table("tenants").select("id").eq("id", tenant_id).execute().data:
        raise AppError(404, "not_found", "Loja não encontrada.")
    return {
        "contacts": sb.table("contacts").select("id", count="exact").eq("tenant_id", tenant_id).execute().count,
        "deals": sb.table("deals").select("id", count="exact").eq("tenant_id", tenant_id).execute().count,
        "suppliers": sb.table("suppliers").select("id", count="exact").eq("tenant_id", tenant_id).execute().count,
        "users": sb.table("user_profiles").select("id", count="exact").eq("tenant_id", tenant_id).execute().count,
    }


def delete_tenant(tenant_id: str) -> None:
    sb = get_service_client()
    if not sb.table("tenants").select("id").eq("id", tenant_id).execute().data:
        raise AppError(404, "not_found", "Loja não encontrada.")

    # Exclusão intencional e definitiva: em vez de bloquear quando a loja já
    # tem dado real (o aviso de risco com a contagem é responsabilidade do
    # frontend, via get_tenant_deletion_summary, antes de chamar isto),
    # cascateia a remoção de tudo vinculado. Todas as FKs pra tenants (e
    # entre essas tabelas) são NO ACTION, não CASCADE — a ordem importa:
    # filhos antes de pais, e user_profiles por último, já que
    # deals/contacts/connections/expenses/attachments referenciam
    # user_profiles.id (owner_id/user_id/uploaded_by) e quebrariam se o
    # perfil fosse apagado antes.
    sb.table("supplier_price_changes").delete().eq("tenant_id", tenant_id).execute()
    sb.table("attachments").delete().eq("tenant_id", tenant_id).execute()
    sb.table("appointments").delete().eq("tenant_id", tenant_id).execute()
    sb.table("activities").delete().eq("tenant_id", tenant_id).execute()
    sb.table("messages").delete().eq("tenant_id", tenant_id).execute()
    sb.table("conversations").delete().eq("tenant_id", tenant_id).execute()
    sb.table("supplier_products").delete().eq("tenant_id", tenant_id).execute()
    sb.table("suppliers").delete().eq("tenant_id", tenant_id).execute()
    sb.table("deals").delete().eq("tenant_id", tenant_id).execute()
    sb.table("contacts").delete().eq("tenant_id", tenant_id).execute()
    sb.table("connections").delete().eq("tenant_id", tenant_id).execute()
    sb.table("expenses").delete().eq("tenant_id", tenant_id).execute()

    # user_profiles.id referencia auth.users(id) on delete cascade — apagar o
    # usuário via Auth Admin já remove a linha de user_profiles (e a conta de
    # login) junto, em vez de deixar uma conta órfã apontando pra um tenant
    # que não existe mais.
    user_profiles = sb.table("user_profiles").select("id").eq("tenant_id", tenant_id).execute().data
    for profile in user_profiles:
        sb.auth.admin.delete_user(profile["id"])

    sb.table("tenants").delete().eq("id", tenant_id).execute()


def update_billing(tenant_id: str, billing_status: str, plan_expires_at: str | None) -> dict:
    sb = get_service_client()
    rows = (
        sb.table("tenants")
        .update({"billing_status": billing_status, "plan_expires_at": plan_expires_at})
        .eq("id", tenant_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Loja não encontrada.")
    return rows[0]
