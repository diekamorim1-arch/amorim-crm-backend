from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role
from app.modules.admin import service
from app.modules.admin.schemas import AdminUserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
def list_all_users(_: AuthContext = Depends(require_role("admin_saas"))):
    return service.list_all_users()
