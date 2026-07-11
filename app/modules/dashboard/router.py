from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import require_role
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardMetrics, MonthlyDealDetail, MonthlyHistoryItem

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(user: AuthContext = Depends(require_role("gestor"))):
    return service.get_metrics(user.tenant_id)


@router.get("/monthly-history", response_model=list[MonthlyHistoryItem])
def monthly_history(
    months: int = Query(default=12, ge=1, le=36),
    user: AuthContext = Depends(require_role("gestor")),
):
    return service.get_monthly_history(user.tenant_id, months)


@router.get("/monthly-history/{year}/{month}", response_model=list[MonthlyDealDetail])
def monthly_detail(year: int, month: int, user: AuthContext = Depends(require_role("gestor"))):
    return service.get_monthly_detail(user.tenant_id, year, month)
