from fastapi import APIRouter, Depends, File, UploadFile

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.attachments import service
from app.modules.attachments.schemas import AttachmentOut

router = APIRouter(tags=["attachments"])


@router.get("/contacts/{contact_id}/attachments", response_model=list[AttachmentOut])
def list_all(contact_id: str, tenant_id: str = Depends(require_tenant)):
    return service.list_attachments(tenant_id, contact_id)


@router.post("/contacts/{contact_id}/attachments", response_model=AttachmentOut)
async def create(
    contact_id: str,
    file: UploadFile = File(...),
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    content = await file.read()
    return service.create_attachment(
        tenant_id,
        user.user_id,
        contact_id,
        file.filename or "arquivo",
        file.content_type or "application/octet-stream",
        content,
    )


@router.delete("/attachments/{attachment_id}")
def delete(
    attachment_id: str,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    service.delete_attachment(tenant_id, user.user_id, attachment_id)
    return {"status": "deleted"}
