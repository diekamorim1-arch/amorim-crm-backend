from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import get_current_user
from app.modules.auth.schemas import MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(user: AuthContext = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=user.user_id, tenant_id=user.tenant_id, role=user.role, email=user.email)
