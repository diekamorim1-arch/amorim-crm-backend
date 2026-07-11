from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role, require_tenant
from app.modules.deals import service
from app.modules.deals.schemas import (
    DealCreate,
    DealFinancialsUpdate,
    DealOut,
    DealUpdate,
    LeadCreate,
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


@router.post("/leads", response_model=DealOut)
def create_lead(
    body: LeadCreate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_lead(
        tenant_id, user.user_id, body.name, body.whatsapp, body.origin, body.product_line, body.value,
        body.owner_id, user.is_impersonating,
    )


@router.post("/deals", response_model=DealOut)
def create(
    body: DealCreate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_deal(tenant_id, user.user_id, body.model_dump(), user.is_impersonating)


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update(
    deal_id: str,
    body: DealUpdate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.update_deal(tenant_id, user.user_id, deal_id, body.model_dump())


@router.delete("/deals/{deal_id}")
def delete(
    deal_id: str,
    user: AuthContext = Depends(require_role("gestor")),
    tenant_id: str = Depends(require_tenant),
):
    service.delete_deal(tenant_id, user.user_id, deal_id)
    return {"status": "deleted"}


@router.post("/deals/{deal_id}/move", response_model=DealOut)
def move(deal_id: str, body: MoveDealBody, user: AuthContext = Depends(get_current_user)):
    return service.move_deal(user.tenant_id, deal_id, body.stage, user.user_id)


@router.post("/deals/{deal_id}/mark-lost", response_model=DealOut)
def mark_lost(
    deal_id: str,
    body: MarkLostBody,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.mark_lost(tenant_id, user.user_id, deal_id, body.reason)


@router.patch("/deals/{deal_id}/financials", response_model=DealOut)
def update_financials(deal_id: str, body: DealFinancialsUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_financials(
        user.tenant_id, user.user_id, deal_id,
        body.supplier_product_id, body.supplier_value, body.gift_value, body.freight_value,
    )
