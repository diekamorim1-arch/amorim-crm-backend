from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role
from app.modules.tenants import service
from app.modules.tenants.schemas import (
    ImpersonateResponse,
    TenantCreate,
    TenantOut,
    TenantSettingsUpdate,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
def list_all(_: AuthContext = Depends(require_role("admin_saas"))):
    return service.list_tenants()


@router.post("", response_model=TenantOut)
def create(body: TenantCreate, _: AuthContext = Depends(require_role("admin_saas"))):
    return service.create_tenant(body.name, body.plan)


@router.patch("/{tenant_id}", response_model=TenantOut)
def update(tenant_id: str, body: TenantUpdate, user: AuthContext = Depends(get_current_user)):
    return service.update_tenant(
        tenant_id, user.tenant_id, user.role, user.role == "admin_saas", body.name, body.plan
    )


@router.patch("/{tenant_id}/settings", response_model=TenantOut)
def update_settings(tenant_id: str, body: TenantSettingsUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_tenant_settings(tenant_id, user.tenant_id, body.model_dump())


@router.post("/{tenant_id}/impersonate", response_model=ImpersonateResponse)
def impersonate(tenant_id: str, _: AuthContext = Depends(require_role("admin_saas"))):
    tenant = service.check_tenant_for_impersonation(tenant_id)
    return ImpersonateResponse(tenant_id=tenant["id"], tenant_name=tenant["name"])
