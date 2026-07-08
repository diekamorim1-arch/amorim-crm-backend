from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    tenant_id: str | None
    role: str
    name: str
    avatar_color: str


class UserInvite(BaseModel):
    name: str
    email: str
    role: str


class UserRoleUpdate(BaseModel):
    role: str
