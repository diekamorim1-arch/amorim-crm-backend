from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role, require_tenant
from app.modules.contacts import service
from app.modules.contacts.schemas import ContactCreate, ContactDeletionSummary, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    journey_status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    return service.list_contacts(tenant_id, journey_status, tag, origin, owner_id, search)


@router.get("/{contact_id}", response_model=ContactOut)
def get(contact_id: str, tenant_id: str = Depends(require_tenant)):
    return service.get_contact(tenant_id, contact_id)


@router.post("", response_model=ContactOut)
def create(
    body: ContactCreate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_contact(tenant_id, user.user_id, body.model_dump(), background_tasks, user.is_impersonating)


@router.patch("/{contact_id}", response_model=ContactOut)
def update(
    contact_id: str,
    body: ContactUpdate,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.update_contact(
        tenant_id, user.user_id, contact_id, body.model_dump(), background_tasks, user.is_impersonating
    )


@router.get("/{contact_id}/deletion-summary", response_model=ContactDeletionSummary)
def deletion_summary(contact_id: str, tenant_id: str = Depends(require_tenant), _: AuthContext = Depends(require_role("gestor"))):
    return service.get_contact_deletion_summary(tenant_id, contact_id)


@router.delete("/{contact_id}")
def delete(
    contact_id: str,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(require_role("gestor")),
    tenant_id: str = Depends(require_tenant),
):
    service.delete_contact(tenant_id, user.user_id, contact_id, background_tasks)
    return {"status": "deleted"}
