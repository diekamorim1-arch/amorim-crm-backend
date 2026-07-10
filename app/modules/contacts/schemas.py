from pydantic import BaseModel


class Address(BaseModel):
    street: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""


class ContactOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    whatsapp: str
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    origin: str
    interests: list[str]
    tags: list[str]
    journey_status: str
    owner_id: str
    first_contact_at: str
    last_interaction_at: str


class ContactCreate(BaseModel):
    name: str
    whatsapp: str
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    origin: str
    interests: list[str] = []
    tags: list[str] = []
    owner_id: str


class ContactUpdate(BaseModel):
    name: str | None = None
    whatsapp: str | None = None
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    origin: str | None = None
    interests: list[str] | None = None
    tags: list[str] | None = None
    owner_id: str | None = None
