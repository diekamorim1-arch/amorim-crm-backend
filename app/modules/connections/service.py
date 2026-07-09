import httpx

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_connections(tenant_id: str, user_id: str, role: str) -> list[dict]:
    sb = get_service_client()
    query = sb.table("connections").select("*").eq("tenant_id", tenant_id)
    if role != "gestor":
        query = query.eq("user_id", user_id)
    return query.execute().data


def _get_connection(sb, tenant_id: str, connection_id: str) -> dict:
    # connection_id não é uma referência externa vinda do body (como contact_id
    # em activities/appointments) — é o próprio recurso sendo buscado, e a
    # busca já filtra por tenant_id. Um connection_id de outro tenant não
    # retorna linha nenhuma aqui, então cai no 404 abaixo por construção; não
    # há necessidade de um verify_owned_by_tenant adicional.
    rows = sb.table("connections").select("*").eq("tenant_id", tenant_id).eq("id", connection_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Conexão não encontrada.")
    return rows[0]


def _assert_can_manage(connection: dict, caller_user_id: str, caller_role: str) -> None:
    # Access model: atendente só gerencia a própria conexão; gestor gerencia
    # qualquer uma do tenant. `_get_connection` só escopa por tenant_id (ver
    # comentário acima), então sem esta checagem um atendente poderia
    # parear/desconectar a conexão de outro usuário do mesmo tenant.
    if caller_role != "gestor" and connection["user_id"] != caller_user_id:
        raise AppError(403, "forbidden", "Você só pode gerenciar a própria conexão.")


def pair(tenant_id: str, connection_id: str, caller_user_id: str, caller_role: str) -> dict:
    sb = get_service_client()
    connection = _get_connection(sb, tenant_id, connection_id)
    _assert_can_manage(connection, caller_user_id, caller_role)
    settings = get_settings()
    if settings.evolution_api_url:
        response = httpx.post(
            f"{settings.evolution_api_url}/instance/create",
            headers={"apikey": settings.evolution_api_key},
            json={"instanceName": connection_id},
            timeout=10,
        )
        response.raise_for_status()
    return sb.table("connections").update({"status": "pareando"}).eq("id", connection_id).execute().data[0]


def disconnect(tenant_id: str, connection_id: str, caller_user_id: str, caller_role: str) -> dict:
    sb = get_service_client()
    connection = _get_connection(sb, tenant_id, connection_id)
    _assert_can_manage(connection, caller_user_id, caller_role)
    settings = get_settings()
    if settings.evolution_api_url:
        httpx.delete(
            f"{settings.evolution_api_url}/instance/logout/{connection_id}",
            headers={"apikey": settings.evolution_api_key},
            timeout=10,
        )
    return sb.table("connections").update({"status": "desconectado"}).eq("id", connection_id).execute().data[0]
