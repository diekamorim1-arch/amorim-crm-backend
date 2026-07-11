from typing import Literal

from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    tenant_id: str | None
    role: str
    name: str
    email: str
    avatar_color: str
    avatar_url: str | None = None
    is_active: bool = True
    notifications_last_seen_at: str | None = None


class UserInvite(BaseModel):
    name: str
    email: str
    role: Literal["atendente", "gestor"]


class UserRoleUpdate(BaseModel):
    role: Literal["atendente", "gestor"]


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


class UserStatusUpdate(BaseModel):
    is_active: bool


class MeUpdate(BaseModel):
    name: str | None = None
