from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.activities import service
from app.modules.activities.schemas import ActivityCreate, ActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
def list_all(contact_id: str = Query(...), tenant_id: str = Depends(require_tenant)):
    return service.list_activities(tenant_id, contact_id)


@router.get("/recent", response_model=list[ActivityOut])
def list_recent(limit: int = Query(default=20, ge=1, le=100), tenant_id: str = Depends(require_tenant)):
    return service.list_recent_activities(tenant_id, limit)


@router.post("", response_model=ActivityOut)
def create(body: ActivityCreate, user: AuthContext = Depends(get_current_user)):
    return service.create_activity(user.tenant_id, user.user_id, body.model_dump())
