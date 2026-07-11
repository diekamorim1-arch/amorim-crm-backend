import os
import uuid

# Antes de qualquer import de app.* (que carrega app.config.get_settings(),
# cacheado com @lru_cache): força EVOLUTION_API_URL/EVOLUTION_API_KEY vazios
# nesta sessão de teste, não importa o que esteja no .env do dev local. Vários
# testes (ex.: test_qrcode_retorna_503_quando_evolution_nao_configurada)
# dependem desse caminho "Evolution não configurada" — variável de ambiente
# tem precedência sobre .env no pydantic-settings, então isso vale mesmo com
# EVOLUTION_API_URL preenchido em .env pra rodar o backend manualmente contra
# a Evolution local de verdade (ver .env.evolution-local).
os.environ["EVOLUTION_API_URL"] = ""
os.environ["EVOLUTION_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from app.config import get_settings
from app.core.supabase_client import get_service_client
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def test_tenant():
    sb = get_service_client()
    slug = f"teste-{uuid.uuid4().hex[:8]}"
    tenant = sb.table("tenants").insert({"name": "Loja de Teste", "slug": slug}).execute().data[0]
    yield tenant
    # user_profiles.tenant_id tem FK para tenants.id: precisa remover os perfis
    # de teste (atendente/gestor) criados sob este tenant antes de apagá-lo,
    # senão o delete abaixo falha com violação de FK.
    sb.table("user_profiles").delete().eq("tenant_id", tenant["id"]).execute()
    # audit_log.record_id não tem FK (log genérico, append-only) — não bloqueia
    # a ordem de limpeza acima, mas ainda assim limpamos aqui pra manter o
    # banco vazio ao final da suíte, já que create_contact/deals etc. (Parte 3)
    # agora gravam auditoria a cada teste que passa por este tenant.
    sb.table("audit_log").delete().eq("tenant_id", tenant["id"]).execute()
    sb.table("tenants").delete().eq("id", tenant["id"]).execute()


def _create_user_and_sign_in(sb, tenant_id: str | None, role: str) -> tuple[str, str]:
    """Cria um usuário real de teste e loga. Retorna (access_token, user_id) —
    o id vem direto da resposta de criação, nunca decodificado do JWT depois
    (o projeto não usa mais PyJWT em lugar nenhum, ver Task 3 Step 4).

    O sign-in é feito com um client Supabase novo (chave anon, como um cliente
    real faria), nunca com `sb` (o client de service role, singleton
    cacheado por `get_service_client()`): `sign_in_with_password` reatribui,
    em memória, o header Authorization do client usado para o token do
    usuário logado (`supabase/_sync/client.py::_listen_to_auth_events`) — se
    fosse chamado em `sb`, o client de service role compartilhado por toda a
    suíte (e pela app) ficaria "rebaixado" ao token desse usuário para
    sempre, quebrando qualquer `admin.create_user`/query com bypass de RLS
    subsequente no mesmo processo.
    """
    email = f"{role}.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br"
    password = "SenhaDeTeste123!"
    app_metadata = {"role": role} if tenant_id is None else {"tenant_id": tenant_id, "role": role}
    created = sb.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True, "app_metadata": app_metadata}
    )
    user_id = created.user.id
    sb.table("user_profiles").insert(
        {"id": user_id, "tenant_id": tenant_id, "role": role, "name": f"Teste {role.title()}"}
    ).execute()
    settings = get_settings()
    sign_in_client = create_client(settings.supabase_url, settings.supabase_anon_key)
    session = sign_in_client.auth.sign_in_with_password({"email": email, "password": password})
    return session.session.access_token, user_id


@pytest.fixture(scope="session")
def _atendente(test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "atendente")
    yield token, user_id
    # user_profiles.id referencia auth.users(id) on delete cascade (Task 2), mas
    # apagamos a linha explicitamente antes como salvaguarda caso a cascade não
    # dispare por algum motivo — delete_user sozinho já é suficiente hoje
    # (confirmado manualmente), mas isso não deve ficar implícito.
    sb.table("user_profiles").delete().eq("id", user_id).execute()
    sb.auth.admin.delete_user(user_id)


@pytest.fixture(scope="session")
def atendente_token(_atendente) -> str:
    return _atendente[0]


@pytest.fixture(scope="session")
def atendente_user_id(_atendente) -> str:
    return _atendente[1]


@pytest.fixture(scope="session")
def _gestor(test_tenant):
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, test_tenant["id"], "gestor")
    yield token, user_id
    sb.table("user_profiles").delete().eq("id", user_id).execute()
    sb.auth.admin.delete_user(user_id)


@pytest.fixture(scope="session")
def gestor_token(_gestor) -> str:
    return _gestor[0]


@pytest.fixture(scope="session")
def gestor_user_id(_gestor) -> str:
    return _gestor[1]


@pytest.fixture(scope="session")
def _admin():
    sb = get_service_client()
    token, user_id = _create_user_and_sign_in(sb, None, "admin_saas")
    yield token, user_id
    # tenant_id é None aqui, então o delete por tenant_id em test_tenant nunca
    # alcança esta linha — precisa ser removida aqui mesmo.
    sb.table("user_profiles").delete().eq("id", user_id).execute()
    sb.auth.admin.delete_user(user_id)


@pytest.fixture(scope="session")
def admin_token(_admin) -> str:
    return _admin[0]


@pytest.fixture(scope="session")
def admin_user_id(_admin) -> str:
    return _admin[1]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
