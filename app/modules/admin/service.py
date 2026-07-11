from app.core.supabase_client import get_service_client
from app.modules.users.service import with_email


def list_all_users() -> list[dict]:
    # Join embutido (user_profiles -> tenants via FK) pra trazer o nome da
    # loja de cada usuário numa única query — sem isso, cada linha exigiria
    # uma consulta extra pra resolver tenant_id -> nome. admin_saas aparece
    # com tenant_name=None (não pertence a loja nenhuma).
    sb = get_service_client()
    rows = sb.table("user_profiles").select("*, tenants(name)").execute().data
    result = []
    for row in rows:
        tenant = row.pop("tenants", None)
        enriched = with_email(sb, row)
        enriched["tenant_name"] = tenant["name"] if tenant else None
        result.append(enriched)
    return result
