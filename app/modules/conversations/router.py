from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.conversations import service
from app.modules.conversations.schemas import (
    AssigneeUpdate,
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    assignee_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    return service.list_conversations(tenant_id, assignee_id, status)


@router.post("", response_model=ConversationOut)
def create(body: ConversationCreate, tenant_id: str = Depends(require_tenant)):
    return service.create_conversation(tenant_id, body.contact_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: str, tenant_id: str = Depends(require_tenant)):
    return service.get_messages(tenant_id, conversation_id)


@router.post("/{conversation_id}/messages", response_model=MessageOut)
def send_message(conversation_id: str, body: MessageCreate, user: AuthContext = Depends(get_current_user)):
    return service.send_message(user.tenant_id, conversation_id, body.text, user.user_id)


@router.patch("/{conversation_id}/assignee", response_model=ConversationOut)
def update_assignee(conversation_id: str, body: AssigneeUpdate, tenant_id: str = Depends(require_tenant)):
    return service.update_assignee(tenant_id, conversation_id, body.assignee_id)
