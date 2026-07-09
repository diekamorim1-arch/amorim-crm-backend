from pydantic import BaseModel


class DealOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    title: str
    products: str
    value: float
    payment: str
    trade_in: bool
    trade_in_desc: str | None = None
    stage: str
    outcome: str
    loss_reason: str | None = None
    owner_id: str
    stage_changed_at: str
    supplier_product_id: str | None = None
    supplier_value: float | None = None
    gift_value: float | None = None


class LeadCreate(BaseModel):
    name: str
    whatsapp: str
    origin: str
    product_line: str | None = None
    value: float
    owner_id: str


class DealCreate(BaseModel):
    contact_id: str
    title: str
    products: str
    value: float
    payment: str
    trade_in: bool = False
    trade_in_desc: str | None = None
    owner_id: str


class DealUpdate(BaseModel):
    title: str | None = None
    products: str | None = None
    value: float | None = None
    payment: str | None = None


class MoveDealBody(BaseModel):
    stage: str


class MarkLostBody(BaseModel):
    reason: str


class DealFinancialsUpdate(BaseModel):
    supplier_product_id: str | None = None
    supplier_value: float
    gift_value: float
