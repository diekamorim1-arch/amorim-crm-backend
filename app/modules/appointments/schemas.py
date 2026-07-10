from pydantic import BaseModel


class AppointmentOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    deal_id: str | None = None
    type: str
    starts_at: str
    ends_at: str
    status: str
    owner_id: str
    note: str | None = None


class AppointmentCreate(BaseModel):
    contact_id: str
    deal_id: str | None = None
    type: str
    starts_at: str
    ends_at: str
    owner_id: str
    note: str | None = None


class AppointmentUpdate(BaseModel):
    contact_id: str | None = None
    deal_id: str | None = None
    type: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    status: str | None = None
    owner_id: str | None = None
    note: str | None = None
