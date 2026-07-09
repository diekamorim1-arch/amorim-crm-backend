from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import require_role, require_tenant
from app.modules.suppliers import service
from app.modules.suppliers.schemas import (
    PriceChangeOut,
    PriceUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierUpdate,
)

router = APIRouter(tags=["suppliers"])


@router.get("/suppliers", response_model=list[SupplierOut])
def list_all(tenant_id: str = Depends(require_tenant), search: str | None = Query(default=None)):
    return service.list_suppliers(tenant_id, search)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get(supplier_id: str, tenant_id: str = Depends(require_tenant)):
    return service.get_supplier(tenant_id, supplier_id)


@router.post("/suppliers", response_model=SupplierOut)
def create(body: SupplierCreate, user: AuthContext = Depends(require_role("gestor"))):
    return service.create_supplier(user.tenant_id, body.model_dump())


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update(supplier_id: str, body: SupplierUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_supplier(user.tenant_id, supplier_id, body.model_dump())


@router.get("/suppliers/{supplier_id}/products", response_model=list[SupplierProductOut])
def list_products(supplier_id: str, tenant_id: str = Depends(require_tenant)):
    return service.list_products(tenant_id, supplier_id)


@router.post("/suppliers/{supplier_id}/products", response_model=SupplierProductOut)
def create_product(supplier_id: str, body: SupplierProductCreate, user: AuthContext = Depends(require_role("gestor"))):
    return service.create_product(user.tenant_id, supplier_id, body.name, body.current_price)


@router.patch("/supplier-products/{product_id}/price", response_model=SupplierProductOut)
def update_price(product_id: str, body: PriceUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_price(user.tenant_id, product_id, body.price)


@router.get("/supplier-products/{product_id}/price-history", response_model=list[PriceChangeOut])
def get_price_history(product_id: str, tenant_id: str = Depends(require_tenant)):
    return service.price_history(tenant_id, product_id)
