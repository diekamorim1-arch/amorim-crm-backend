import uuid

from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant


def list_users(tenant_id: str) -> list[dict]:
    sb = get_service_client()
    return sb.table("user_profiles").select("*").eq("tenant_id", tenant_id).execute().data


def invite_user(tenant_id: str, name: str, email: str, role: str) -> dict:
    sb = get_service_client()
    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
            "app_metadata": {"tenant_id": tenant_id, "role": role},
        }
    )
    return (
        sb.table("user_profiles")
        .insert({"id": created.user.id, "tenant_id": tenant_id, "role": role, "name": name})
        .execute()
        .data[0]
    )


def update_role(user_id: str, role: str, tenant_id: str) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", user_id, tenant_id, "Usuário não encontrado.")
    sb.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": role}})
    return (
        sb.table("user_profiles")
        .update({"role": role})
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
        .data[0]
    )
