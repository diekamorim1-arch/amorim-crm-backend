from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: str
    tenant_id: str | None
    tenant_name: str | None
    role: str
    name: str
    email: str
    avatar_color: str
    avatar_url: str | None = None
    is_active: bool = True
