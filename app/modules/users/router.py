from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role, require_tenant
from app.modules.users import service
from app.modules.users.schemas import UserInvite, UserOut, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_all(tenant_id: str = Depends(require_tenant)):
    return service.list_users(tenant_id)


@router.post("/invite", response_model=UserOut)
def invite(body: UserInvite, user: AuthContext = Depends(require_role("gestor"))):
    return service.invite_user(user.tenant_id, body.name, body.email, body.role)


@router.patch("/{user_id}/role", response_model=UserOut)
def update_role(user_id: str, body: UserRoleUpdate, _: AuthContext = Depends(require_role("gestor"))):
    return service.update_role(user_id, body.role)
