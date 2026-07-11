from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.appointments import service
from app.modules.appointments.schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    contact_id: str | None = Query(default=None),
):
    return service.list_appointments(tenant_id, date_from, date_to, contact_id)


@router.post("", response_model=AppointmentOut)
def create(
    body: AppointmentCreate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.create_appointment(tenant_id, body.model_dump(), user.user_id, user.is_impersonating)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update(
    appointment_id: str,
    body: AppointmentUpdate,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    return service.update_appointment(tenant_id, appointment_id, body.model_dump(), user.user_id, user.is_impersonating)
