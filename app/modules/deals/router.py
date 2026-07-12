from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role, require_tenant
from app.modules.deals import service
from app.modules.deals.schemas import (
    DealCreate,
    DealFinancialsUpdate,
    DealOut,
    DealUpdate,
    LeadCreate,
    LeadCreateOut,
    MarkLostBody,
    MoveDealBody,
)

router = APIRouter(tags=["deals"])


@router.get("/deals", response_model=list[DealOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    stage: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    contact_id: str | None = Query(default=None),
):
    return service.list_deals(tenant_id, stage, outcome, owner_id, contact_id)


@router.post("/leads", response_model=LeadCreateOut)
def create_lead(
    body: LeadCreate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_lead(
        tenant_id, user.user_id, body.name, body.whatsapp, body.origin, body.product_line, body.value,
        body.owner_id, body.supplier_product_id, body.supplier_value, background_tasks, user.is_impersonating,
    )


@router.post("/deals", response_model=DealOut)
def create(
    body: DealCreate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_deal(tenant_id, user.user_id, body.model_dump(), background_tasks, user.is_impersonating)


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update(
    deal_id: str,
    body: DealUpdate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.update_deal(tenant_id, user.user_id, deal_id, body.model_dump(), background_tasks)


@router.delete("/deals/{deal_id}")
def delete(
    deal_id: str,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(require_role("gestor")),
    tenant_id: str = Depends(require_tenant),
):
    service.delete_deal(tenant_id, user.user_id, deal_id, background_tasks)
    return {"status": "deleted"}


@router.post("/deals/{deal_id}/move", response_model=DealOut)
def move(deal_id: str, body: MoveDealBody, background_tasks: BackgroundTasks, user: AuthContext = Depends(get_current_user)):
    return service.move_deal(user.tenant_id, deal_id, body.stage, user.user_id, background_tasks)


@router.post("/deals/{deal_id}/mark-lost", response_model=DealOut)
def mark_lost(
    deal_id: str,
    body: MarkLostBody,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.mark_lost(tenant_id, user.user_id, deal_id, body.reason, background_tasks)


@router.patch("/deals/{deal_id}/financials", response_model=DealOut)
def update_financials(
    deal_id: str,
    body: DealFinancialsUpdate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(require_role("gestor")),
):
    return service.update_financials(
        user.tenant_id, user.user_id, deal_id,
        body.supplier_product_id, body.supplier_value, body.gift_value, body.freight_value, background_tasks,
    )
