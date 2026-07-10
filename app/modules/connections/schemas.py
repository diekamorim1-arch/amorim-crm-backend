from pydantic import BaseModel


class ConnectionOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    phone: str
    status: str
    connected_at: str | None = None


class ConnectionCreate(BaseModel):
    phone: str = ""


class QrCodeOut(BaseModel):
    qrcode: str | None = None
    status: str


class SendMessageIn(BaseModel):
    number: str
    text: str


class SendMessageOut(BaseModel):
    status: str
