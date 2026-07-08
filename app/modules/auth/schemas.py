from pydantic import BaseModel


class MeResponse(BaseModel):
    id: str
    tenant_id: str | None
    role: str
    email: str
