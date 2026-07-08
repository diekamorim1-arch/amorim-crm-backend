from app.core.supabase_client import get_service_client


def test_service_client_can_query_tenants():
    client = get_service_client()
    response = client.table("tenants").select("id").limit(1).execute()
    assert isinstance(response.data, list)
