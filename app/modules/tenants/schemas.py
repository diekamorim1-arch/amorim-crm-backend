from pydantic import BaseModel


class TenantSettings(BaseModel):
    tags: list[str] = []
    loss_reasons: list[str] = []
    business_hours: str = ""


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    settings: TenantSettings


class TenantCreate(BaseModel):
    name: str
    plan: str = "starter"


class TenantUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None


class TenantSettingsUpdate(BaseModel):
    tags: list[str] | None = None
    loss_reasons: list[str] | None = None
    business_hours: str | None = None


class ImpersonateResponse(BaseModel):
    tenant_id: str
    tenant_name: str
