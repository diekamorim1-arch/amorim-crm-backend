from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    deal_id: str | None = None
    file_name: str
    file_type: str
    uploaded_by: str
    uploaded_at: str
    url: str
