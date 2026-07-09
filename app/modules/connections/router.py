from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import get_current_user
from app.modules.connections import service
from app.modules.connections.schemas import ConnectionOut

router = APIRouter(prefix="/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionOut])
def list_all(user: AuthContext = Depends(get_current_user)):
    return service.list_connections(user.tenant_id, user.user_id, user.role)


@router.post("/{connection_id}/pair", response_model=ConnectionOut)
def pair(connection_id: str, user: AuthContext = Depends(get_current_user)):
    return service.pair(user.tenant_id, connection_id)


@router.post("/{connection_id}/disconnect", response_model=ConnectionOut)
def disconnect(connection_id: str, user: AuthContext = Depends(get_current_user)):
    return service.disconnect(user.tenant_id, connection_id)
