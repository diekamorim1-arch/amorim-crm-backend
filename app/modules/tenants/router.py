from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.core.errors import AppError
from app.deps import get_current_user, require_role
from app.modules.tenants import service
from app.modules.tenants.schemas import (
    ImpersonateResponse,
    TenantBillingUpdate,
    TenantCreate,
    TenantDeletionSummary,
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


@router.get("/{tenant_id}", response_model=TenantOut)
def get_one(tenant_id: str, user: AuthContext = Depends(get_current_user)):
    if user.role != "admin_saas" and user.tenant_id != tenant_id:
        raise AppError(403, "forbidden", "Você só pode ver a própria loja.")
    return service.get_tenant(tenant_id)


@router.patch("/{tenant_id}", response_model=TenantOut)
def update(tenant_id: str, body: TenantUpdate, user: AuthContext = Depends(get_current_user)):
    return service.update_tenant(
        tenant_id, user.tenant_id, user.role, user.role == "admin_saas", body.name, body.plan
    )


@router.patch("/{tenant_id}/settings", response_model=TenantOut)
def update_settings(tenant_id: str, body: TenantSettingsUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_tenant_settings(tenant_id, user.tenant_id, body.model_dump())


@router.patch("/{tenant_id}/billing", response_model=TenantOut)
def update_billing(tenant_id: str, body: TenantBillingUpdate, _: AuthContext = Depends(require_role("admin_saas"))):
    return service.update_billing(tenant_id, body.billing_status, body.plan_expires_at)


@router.get("/{tenant_id}/deletion-summary", response_model=TenantDeletionSummary)
def deletion_summary(tenant_id: str, _: AuthContext = Depends(require_role("admin_saas"))):
    return service.get_tenant_deletion_summary(tenant_id)


@router.delete("/{tenant_id}")
def delete(tenant_id: str, _: AuthContext = Depends(require_role("admin_saas"))):
    service.delete_tenant(tenant_id)
    return {"status": "deleted"}


@router.post("/{tenant_id}/impersonate", response_model=ImpersonateResponse)
def impersonate(tenant_id: str, _: AuthContext = Depends(require_role("admin_saas"))):
    tenant = service.check_tenant_for_impersonation(tenant_id)
    return ImpersonateResponse(tenant_id=tenant["id"], tenant_name=tenant["name"])
