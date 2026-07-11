from fastapi import APIRouter, Depends, File, UploadFile

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role, require_tenant
from app.modules.users import service
from app.modules.users.schemas import MeUpdate, UserInvite, UserOut, UserRoleUpdate, UserStatusUpdate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_all(tenant_id: str = Depends(require_tenant)):
    return service.list_users(tenant_id)


@router.post("/invite", response_model=UserOut)
def invite(body: UserInvite, user: AuthContext = Depends(require_role("gestor"))):
    return service.invite_user(user.tenant_id, body.name, body.email, body.role)


# /me precisa vir antes de /{user_id} — senão o FastAPI casa "me" com o path
# param {user_id} primeiro (mesmo método, mesmo prefixo) e essas rotas nunca
# seriam alcançadas. Sem restrição de papel/tenant: qualquer usuário
# autenticado (inclusive admin_saas sem tenant) edita só a própria conta.
@router.patch("/me", response_model=UserOut)
def update_me(body: MeUpdate, user: AuthContext = Depends(get_current_user)):
    return service.update_me(user.user_id, body.name)


@router.post("/me/avatar", response_model=UserOut)
async def upload_my_avatar(file: UploadFile = File(...), user: AuthContext = Depends(get_current_user)):
    content = await file.read()
    return service.upload_avatar(user.user_id, file.filename or "avatar", file.content_type or "application/octet-stream", content)


@router.post("/me/notifications-seen", response_model=UserOut)
def mark_notifications_seen(user: AuthContext = Depends(get_current_user)):
    return service.mark_notifications_seen(user.user_id)


@router.patch("/{user_id}/role", response_model=UserOut)
def update_role(user_id: str, body: UserRoleUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_role(user_id, body.role, user.tenant_id)


@router.patch("/{user_id}", response_model=UserOut)
def update(user_id: str, body: UserUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_user(user_id, user.tenant_id, body.name, body.email)


@router.patch("/{user_id}/status", response_model=UserOut)
def update_status(user_id: str, body: UserStatusUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_status(user_id, user.tenant_id, body.is_active, user.user_id)


@router.delete("/{user_id}")
def delete(user_id: str, user: AuthContext = Depends(require_role("gestor"))):
    service.delete_user(user_id, user.tenant_id, user.user_id)
    return {"status": "deleted"}
