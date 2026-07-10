from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.contacts import service
from app.modules.contacts.schemas import ContactCreate, ContactOut, ContactUpdate

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
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_contact(tenant_id, user.user_id, body.model_dump())


@router.patch("/{contact_id}", response_model=ContactOut)
def update(
    contact_id: str,
    body: ContactUpdate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.update_contact(tenant_id, user.user_id, contact_id, body.model_dump())
