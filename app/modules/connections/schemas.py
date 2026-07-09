from pydantic import BaseModel


class ConnectionOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    phone: str
    status: str
    connected_at: str | None = None
