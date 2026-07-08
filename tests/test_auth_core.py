import pytest

from app.core.auth import extract_claims
from app.core.errors import AppError


def test_extract_claims_papel_gestor():
    payload = {
        "sub": "user-123",
        "email": "gestor@amorimimports.com.br",
        "app_metadata": {"tenant_id": "tenant-abc", "role": "gestor"},
    }
    ctx = extract_claims(payload)
    assert ctx.user_id == "user-123"
    assert ctx.tenant_id == "tenant-abc"
    assert ctx.role == "gestor"
    assert ctx.email == "gestor@amorimimports.com.br"


def test_extract_claims_admin_saas_sem_tenant():
    payload = {
        "sub": "user-456",
        "email": "diego@amorimcrm.com.br",
        "app_metadata": {"role": "admin_saas"},
    }
    ctx = extract_claims(payload)
    assert ctx.tenant_id is None
    assert ctx.role == "admin_saas"


def test_extract_claims_sem_role_levanta_app_error():
    payload = {"sub": "user-789", "email": "x@x.com", "app_metadata": {}}
    with pytest.raises(AppError) as exc_info:
        extract_claims(payload)
    assert exc_info.value.status_code == 401
