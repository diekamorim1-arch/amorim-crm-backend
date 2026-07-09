from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardMetrics

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(user: AuthContext = Depends(require_role("gestor"))):
    return service.get_metrics(user.tenant_id)
