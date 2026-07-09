from pydantic import BaseModel


class ActivityOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    deal_id: str | None = None
    user_id: str
    type: str
    description: str
    created_at: str


class ActivityCreate(BaseModel):
    contact_id: str
    deal_id: str | None = None
    type: str
    description: str
