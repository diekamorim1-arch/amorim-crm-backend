from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    content = await file.read()
    # Mesmo bug de app/modules/users/router.py::upload_my_avatar —
    # create_attachment é síncrona/bloqueante; run_in_threadpool evita travar
    # o event loop (e todo mundo mais usando o app) durante o upload.
    return await run_in_threadpool(
        service.create_attachment,
        tenant_id,
        user.user_id,
        contact_id,
        file.filename or "arquivo",
        file.content_type or "application/octet-stream",
        content,
        background_tasks,
    )


@router.delete("/attachments/{attachment_id}")
def delete(
    attachment_id: str,
    background_tasks: BackgroundTasks,
    user: AuthContext = Depends(get_current_user),
    tenant_id: str = Depends(require_tenant),
):
    service.delete_attachment(tenant_id, user.user_id, attachment_id, background_tasks)
    return {"status": "deleted"}
