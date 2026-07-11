import uuid
from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client
from app.core.tenant_guard import verify_owned_by_tenant

# Supabase Auth Admin não tem um "ban permanente" — convenção comum é uma
# duração bem longa. "none" desfaz o ban (usado por update_status).
BAN_DURATION_INDEFINITE = "876000h"

AVATAR_BUCKET = "avatars"
# Mesmo valor do MAX_AVATAR_BYTES em src/components/settings/AccountTab.tsx —
# divergir faz uma foto "menor que 2MB" na tela ser rejeitada aqui.
MAX_AVATAR_BYTES = 2_000_000
# HEIC/HEIF (padrão de fotos do iPhone) fica de fora de propósito: o
# frontend converte pra JPEG antes de enviar (a maioria dos navegadores não
# renderiza <img src> HEIC), então um upload que chegue aqui como HEIC
# indica que essa conversão falhou ou foi contornada — melhor rejeitar do
# que salvar um avatar que não abre pra quase ninguém.
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def with_email(sb, row: dict) -> dict:
    # user_profiles não guarda e-mail de propósito (Parte 1: só auth.users é
    # fonte de verdade pra isso) — todo UserOut precisa desse enriquecimento.
    auth_user = sb.auth.admin.get_user_by_id(row["id"])
    return {**row, "email": auth_user.user.email or ""}


def list_users(tenant_id: str) -> list[dict]:
    sb = get_service_client()
    rows = sb.table("user_profiles").select("*").eq("tenant_id", tenant_id).execute().data
    return [with_email(sb, row) for row in rows]


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
    row = (
        sb.table("user_profiles")
        .insert({"id": created.user.id, "tenant_id": tenant_id, "role": role, "name": name})
        .execute()
        .data[0]
    )
    return {**row, "email": email}


def update_role(user_id: str, role: str, tenant_id: str) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", user_id, tenant_id, "Usuário não encontrado.")
    sb.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": role}})
    row = (
        sb.table("user_profiles")
        .update({"role": role})
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
        .data[0]
    )
    return with_email(sb, row)


def update_user(user_id: str, tenant_id: str, name: str | None, email: str | None) -> dict:
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", user_id, tenant_id, "Usuário não encontrado.")
    if email is not None:
        sb.auth.admin.update_user_by_id(user_id, {"email": email})
    if name is not None:
        sb.table("user_profiles").update({"name": name}).eq("id", user_id).eq("tenant_id", tenant_id).execute()
    row = sb.table("user_profiles").select("*").eq("id", user_id).eq("tenant_id", tenant_id).execute().data[0]
    return with_email(sb, row)


def update_status(user_id: str, tenant_id: str, is_active: bool, actor_user_id: str) -> dict:
    if user_id == actor_user_id:
        raise AppError(400, "cannot_deactivate_self", "Você não pode desativar a própria conta.")
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", user_id, tenant_id, "Usuário não encontrado.")
    # Soft: bloqueia login via Supabase Auth (ban_duration) sem apagar a conta
    # nem os vínculos (contacts/deals owner_id) — reversível a qualquer momento.
    sb.auth.admin.update_user_by_id(
        user_id, {"ban_duration": "none" if is_active else BAN_DURATION_INDEFINITE}
    )
    row = (
        sb.table("user_profiles")
        .update({"is_active": is_active})
        .eq("id", user_id)
        .eq("tenant_id", tenant_id)
        .execute()
        .data[0]
    )
    return with_email(sb, row)


def update_me(user_id: str, name: str | None) -> dict:
    # Sem verify_owned_by_tenant: quem chama /users/me só pode agir sobre o
    # próprio user_id (vem do token, não de um path param), então não há
    # risco de cruzar tenant — inclusive serve pro admin_saas, que não tem
    # tenant_id nenhum.
    sb = get_service_client()
    if name is not None:
        sb.table("user_profiles").update({"name": name}).eq("id", user_id).execute()
    row = sb.table("user_profiles").select("*").eq("id", user_id).execute().data[0]
    return with_email(sb, row)


def mark_notifications_seen(user_id: str) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    sb.table("user_profiles").update({"notifications_last_seen_at": now}).eq("id", user_id).execute()
    row = sb.table("user_profiles").select("*").eq("id", user_id).execute().data[0]
    return with_email(sb, row)


def upload_avatar(user_id: str, file_name: str, file_type: str, content: bytes) -> dict:
    if len(content) > MAX_AVATAR_BYTES:
        raise AppError(413, "file_too_large", "Imagem maior que 2MB.")
    if file_type not in ALLOWED_AVATAR_TYPES:
        raise AppError(415, "unsupported_file_type", "Envie uma imagem (PNG/JPEG/WEBP/GIF).")
    sb = get_service_client()
    storage_path = f"{user_id}/{uuid.uuid4()}-{file_name}"
    # Bucket público (diferente de "attachments"): foto de perfil é exibida
    # pra outros membros da equipe (Topbar/Equipe), então uma URL pública fixa
    # é mais simples que URL assinada com TTL — não é dado sensível.
    sb.storage.from_(AVATAR_BUCKET).upload(storage_path, content, {"content-type": file_type})
    public_url = sb.storage.from_(AVATAR_BUCKET).get_public_url(storage_path)
    sb.table("user_profiles").update({"avatar_url": public_url}).eq("id", user_id).execute()
    row = sb.table("user_profiles").select("*").eq("id", user_id).execute().data[0]
    return with_email(sb, row)


def delete_user(user_id: str, tenant_id: str, actor_user_id: str) -> None:
    if user_id == actor_user_id:
        raise AppError(400, "cannot_delete_self", "Você não pode excluir a própria conta.")
    sb = get_service_client()
    verify_owned_by_tenant("user_profiles", user_id, tenant_id, "Usuário não encontrado.")
    # Exclusão dura quebraria contacts.owner_id/deals.owner_id já atribuídos a
    # esse usuário — em vez de decidir por conta própria o que fazer com esses
    # vínculos (reatribuir? apagar em cascata?), bloqueia e pede pra desativar.
    linked_contact = sb.table("contacts").select("id").eq("owner_id", user_id).limit(1).execute().data
    linked_deal = sb.table("deals").select("id").eq("owner_id", user_id).limit(1).execute().data
    if linked_contact or linked_deal:
        raise AppError(
            409,
            "user_has_links",
            "Este usuário tem clientes ou negócios atribuídos — desative em vez de excluir.",
        )
    sb.table("user_profiles").delete().eq("id", user_id).eq("tenant_id", tenant_id).execute()
    sb.auth.admin.delete_user(user_id)
