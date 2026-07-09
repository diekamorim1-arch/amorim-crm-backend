from pydantic import BaseModel


class ConversationOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    assignee_id: str | None = None
    status: str
    unread: int


class ConversationCreate(BaseModel):
    contact_id: str


class AssigneeUpdate(BaseModel):
    assignee_id: str | None = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    direction: str
    text: str
    author_id: str | None = None
    status: str
    created_at: str


class MessageCreate(BaseModel):
    text: str
