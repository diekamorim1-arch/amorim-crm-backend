from app.core.supabase_client import get_service_client


def log_audit_event(tenant_id: str, user_id: str | None, action: str, table_name: str, record_id: str) -> None:
    # Populado pela aplicação, não por trigger de Postgres: o backend escreve
    # com a service-role key, então auth.uid()/auth.jwt() ficam vazios dentro
    # de um trigger neste fluxo (o PostgREST só preenche essas claims quando a
    # requisição é autenticada com o JWT do próprio usuário). Cada chamador já
    # tem o user_id via AuthContext, então logamos explicitamente aqui.
    sb = get_service_client()
    sb.table("audit_log").insert(
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "table_name": table_name,
            "record_id": record_id,
        }
    ).execute()
