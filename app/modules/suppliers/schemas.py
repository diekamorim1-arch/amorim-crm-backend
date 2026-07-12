from pydantic import BaseModel


class SupplierOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    whatsapp: str
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None
    created_at: str


class SupplierCreate(BaseModel):
    name: str
    whatsapp: str
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    whatsapp: str | None = None
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierProductOut(BaseModel):
    id: str
    tenant_id: str
    supplier_id: str
    name: str
    current_price: float
    colors: str | None = None
    updated_at: str


class SupplierProductCreate(BaseModel):
    name: str
    current_price: float
    colors: str | None = None


class SupplierProductUpdate(BaseModel):
    name: str | None = None
    current_price: float | None = None
    colors: str | None = None


class SupplierProductBulkItem(BaseModel):
    name: str
    current_price: float
    colors: str | None = None


class SupplierProductBulkCreate(BaseModel):
    products: list[SupplierProductBulkItem]


class PriceUpdate(BaseModel):
    price: float


class PriceChangeOut(BaseModel):
    id: str
    tenant_id: str
    supplier_product_id: str
    price: float
    changed_at: str
