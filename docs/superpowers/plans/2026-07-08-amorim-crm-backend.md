# Amorim CRM Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir do zero a API REST em FastAPI que substitui o `localStorage`/reducer do frontend Amorim CRM por persistência real na Supabase, cobrindo os 11 módulos e a autenticação descritos no spec de requisitos de backend.

**Architecture:** FastAPI com um módulo Python por recurso (`app/modules/<recurso>/{router,schemas,service}.py`), cliente Supabase único com **service-role key** (autorização decidida em Python, RLS como rede de segurança), autenticação via JWT emitido pela Supabase Auth e validado localmente via JWKS. Integração com WhatsApp via EvolutionAPI: webhook de entrada, chamada HTTP de saída.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, `supabase-py` (cliente oficial), PyJWT (+ `PyJWKClient`), pytest + pytest-asyncio + httpx (testes de integração contra o projeto Supabase real), python-dotenv.

## Global Constraints

- Projeto novo em `D:\Skills Claude\amorim-crm-backend`, git próprio (`git init`, branch `main`) — não mexe no repo do frontend.
- Supabase project id: `bkyztodycgvhagzcubes` (schema `public` vazio, já confirmado disponível). Toda migration desta leva usa **este** project id.
- Todo texto de erro/mensagem voltado a log ou resposta HTTP em pt-BR, no mesmo tom do frontend (sentence case, direto).
- Toda tabela (exceto `tenants`) tem `tenant_id uuid not null references tenants(id)`; toda query de leitura/escrita nos módulos de recurso filtra explicitamente por `tenant_id` no Python — nunca confiar só na RLS.
- `config.py` centraliza toda configuração via `pydantic_settings.BaseSettings` após `load_dotenv()` explícito (pedido literal do usuário) — nenhum outro arquivo lê `os.environ` diretamente.
- IDs são UUID gerados pelo Postgres (`gen_random_uuid()` como default de coluna) — nenhum código Python gera ID de entidade.
- Datas: `timestamptz` no Postgres, serializadas como ISO 8601 no JSON (comportamento padrão do FastAPI/Pydantic — não precisa de conversão manual).
- Resposta de sucesso = o recurso direto (sem envelope). Resposta de erro = `{"error": {"code": "...", "message": "..."}}` via `AppError` + exception handler central (Task 3) — nenhum endpoint levanta `HTTPException` cru depois da Task 3.
- Papéis: `atendente`, `gestor`, `admin_saas` — todo endpoint gestor-only usa `Depends(require_role("gestor"))`; nenhum módulo reimplementa a checagem de papel manualmente.
- Gate de cada task: `pytest` (suíte completa) verde antes do commit. A partir da Task 3, os testes de integração rodam contra o Supabase real (`bkyztodycgvhagzcubes`) usando um tenant/usuários de teste criados e destruídos pela própria suíte — nunca deixar dado de teste órfão no projeto.
- Use a Supabase MCP (`apply_migration`, `list_tables`, `execute_sql`) para todo DDL — não gerar arquivos `.sql` soltos para rodar manualmente.

---

### Task 1: Scaffold do projeto Python/FastAPI

**Files:**
- Create: `requirements.txt`, `app/__init__.py`, `app/main.py`, `app/config.py`, `.env.example`, `.gitignore`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_health.py`, `README.md`

**Interfaces (Produces — contrato para todas as tasks seguintes):**

```python
# app/config.py
class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    supabase_jwks_url: str  # calculado a partir de supabase_url por padrão
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_webhook_secret: str = ""
    environment: str = "development"

def get_settings() -> Settings: ...  # cacheado via functools.lru_cache
```

```python
# app/main.py
app: FastAPI  # instância única, importada por tests/conftest.py
```

- [ ] **Step 1: Criar a estrutura e o ambiente**

```bash
mkdir -p "D:\Skills Claude\amorim-crm-backend\app" "D:\Skills Claude\amorim-crm-backend\tests"
cd "D:\Skills Claude\amorim-crm-backend"
python -m venv .venv
```

Ativar o venv (Windows/Git Bash): `source .venv/Scripts/activate`

- [ ] **Step 2: `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
python-dotenv==1.0.1
supabase==2.11.0
pyjwt[crypto]==2.10.1
httpx==0.28.1
pytest==8.3.4
pytest-asyncio==0.25.2
```

Run: `pip install -r requirements.txt`

- [ ] **Step 3: `app/config.py`**

```python
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    supabase_jwks_url: str = ""
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_webhook_secret: str = ""
    environment: str = "development"

    @model_validator(mode="after")
    def default_jwks_url(self) -> "Settings":
        if not self.supabase_jwks_url:
            self.supabase_jwks_url = f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: `.env.example`**

```
SUPABASE_URL=https://bkyztodycgvhagzcubes.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_WEBHOOK_SECRET=
ENVIRONMENT=development
```

Copiar para `.env` e preencher `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY` com as chaves reais do projeto `bkyztodycgvhagzcubes` antes de rodar qualquer teste (Task 2 em diante).

- [ ] **Step 5: `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
```

- [ ] **Step 6: `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Amorim CRM API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)
```

- [ ] **Step 8: `tests/test_health.py`**

```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 9: Rodar e confirmar**

Run: `pytest -v`
Expected: `1 passed`

- [ ] **Step 10: `README.md`**

```markdown
# Amorim CRM Backend

API FastAPI que substitui o localStorage do protótipo frontend por persistência real na Supabase.

## Rodando localmente

1. `python -m venv .venv && source .venv/Scripts/activate`
2. `pip install -r requirements.txt`
3. Copiar `.env.example` para `.env` e preencher as chaves da Supabase
4. `uvicorn app.main:app --reload`
5. `pytest -v` para rodar a suíte (a partir da Task 3, os testes usam o projeto Supabase real e criam/limpam um tenant de teste)
```

- [ ] **Step 11: `git init` e commit inicial**

```bash
cd "D:\Skills Claude\amorim-crm-backend"
git init
git add requirements.txt app/ tests/ .env.example .gitignore README.md
git -c user.name="Dieka" -c user.email="diekamorim1@gmail.com" commit -m "chore: scaffold FastAPI + pytest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Schema Supabase completo + cliente de serviço

**Files:**
- Create: `app/core/__init__.py`, `app/core/supabase_client.py`, `tests/test_supabase_client.py`

**Interfaces (Produces):**

```python
# app/core/supabase_client.py
def get_service_client() -> "supabase.Client": ...  # cacheado, usa SERVICE_ROLE_KEY
```

**Schema (aplicado via Supabase MCP, não em arquivo `.sql` solto):**

Todas as tabelas usam `id uuid primary key default gen_random_uuid()` e `created_at timestamptz not null default now()`, omitidos abaixo por brevidade — inclua-os em toda tabela.

```sql
-- tenants
create table tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  plan text not null check (plan in ('starter','pro')) default 'starter',
  status text not null check (status in ('ativo','suspenso')) default 'ativo',
  settings jsonb not null default '{"tags": [], "loss_reasons": [], "business_hours": ""}',
  created_at timestamptz not null default now()
);

-- user_profiles (dados extras sobre auth.users; tenant_id/role vivem no app_metadata do JWT também)
create table user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  tenant_id uuid references tenants(id),
  role text not null check (role in ('atendente','gestor','admin_saas')),
  name text not null,
  avatar_color text not null default '#4f46e5',
  created_at timestamptz not null default now()
);

-- contacts
create table contacts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  name text not null,
  whatsapp text not null,
  instagram text,
  email text,
  cpf text,
  address jsonb,
  origin text not null check (origin in ('instagram_organico','instagram_ads','whatsapp_direto','indicacao','outro')),
  interests text[] not null default '{}',
  tags text[] not null default '{}',
  journey_status text not null check (journey_status in ('lead','cliente','recorrente')) default 'lead',
  owner_id uuid not null references user_profiles(id),
  first_contact_at timestamptz not null default now(),
  last_interaction_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

-- suppliers
create table suppliers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  name text not null,
  whatsapp text not null,
  contact_name text,
  email text,
  notes text,
  created_at timestamptz not null default now()
);

-- supplier_products
create table supplier_products (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  supplier_id uuid not null references suppliers(id),
  name text not null,
  current_price numeric not null,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

-- supplier_price_changes (append-only)
create table supplier_price_changes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  supplier_product_id uuid not null references supplier_products(id),
  price numeric not null,
  changed_at timestamptz not null default now()
);

-- deals
create table deals (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  contact_id uuid not null references contacts(id),
  title text not null,
  products text not null,
  value numeric not null,
  payment text not null check (payment in ('pix','cartao_avista','cartao_parcelado','boleto')),
  trade_in boolean not null default false,
  trade_in_desc text,
  stage text not null check (stage in ('novo_lead','em_atendimento','negociacao','fechamento','pos_venda')),
  outcome text not null check (outcome in ('aberto','ganho','perdido')) default 'aberto',
  loss_reason text check (loss_reason in ('preco','prazo_entrega','sem_modelo','concorrencia','sem_resposta','desistiu')),
  owner_id uuid not null references user_profiles(id),
  expected_close_at timestamptz,
  stage_changed_at timestamptz not null default now(),
  supplier_product_id uuid references supplier_products(id),
  supplier_value numeric,
  gift_value numeric,
  created_at timestamptz not null default now()
);

-- conversations
create table conversations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  contact_id uuid not null references contacts(id),
  assignee_id uuid references user_profiles(id),
  status text not null check (status in ('aberta','resolvida')) default 'aberta',
  unread int not null default 0,
  created_at timestamptz not null default now()
);

-- messages
create table messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  conversation_id uuid not null references conversations(id),
  direction text not null check (direction in ('in','out')),
  text text not null,
  author_id uuid references user_profiles(id),
  status text not null check (status in ('enviada','entregue','lida')) default 'enviada',
  created_at timestamptz not null default now()
);

-- appointments
create table appointments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  contact_id uuid not null references contacts(id),
  deal_id uuid references deals(id),
  type text not null check (type in ('entrega','retirada','atendimento','follow_up')),
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  status text not null check (status in ('agendado','concluido','cancelado')) default 'agendado',
  owner_id uuid not null references user_profiles(id),
  note text,
  created_at timestamptz not null default now()
);

-- activities
create table activities (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  contact_id uuid not null references contacts(id),
  deal_id uuid references deals(id),
  user_id uuid not null references user_profiles(id),
  type text not null check (type in ('mensagem','mudanca_estagio','nota','agendamento','venda')),
  description text not null,
  created_at timestamptz not null default now()
);

-- connections
create table connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id),
  user_id uuid not null references user_profiles(id),
  phone text not null default '',
  status text not null check (status in ('desconectado','pareando','conectado')) default 'desconectado',
  connected_at timestamptz,
  created_at timestamptz not null default now()
);

-- índices por tenant_id (toda query filtra por essa coluna)
create index on contacts (tenant_id);
create index on deals (tenant_id);
create index on suppliers (tenant_id);
create index on supplier_products (tenant_id);
create index on supplier_price_changes (tenant_id);
create index on conversations (tenant_id);
create index on messages (tenant_id);
create index on appointments (tenant_id);
create index on activities (tenant_id);
create index on connections (tenant_id);

-- RLS: habilitado em toda tabela multitenant, policy comparando tenant_id com o claim do JWT.
-- Isso é rede de segurança (FastAPI usa service_role, que ignora RLS) — protege o dia em
-- que Supabase Realtime ou um client direto usarem o papel "authenticated".
alter table contacts enable row level security;
create policy tenant_isolation on contacts using (tenant_id::text = auth.jwt() ->> 'tenant_id');
-- repetir a mesma policy (nome/condição idênticos, só troca a tabela) para:
-- deals, suppliers, supplier_products, supplier_price_changes, conversations,
-- messages, appointments, activities, connections.
```

- [ ] **Step 1: Aplicar o schema via Supabase MCP**

Use a tool `apply_migration` (project_id `bkyztodycgvhagzcubes`) com o SQL acima. Pode dividir em 2-3 chamadas (ex.: uma para as tabelas, outra para os índices, outra para RLS) se preferir — o importante é que ao final todas as 12 tabelas (`tenants`, `user_profiles`, `contacts`, `suppliers`, `supplier_products`, `supplier_price_changes`, `deals`, `conversations`, `messages`, `appointments`, `activities`, `connections`) existam.

- [ ] **Step 2: Confirmar via `list_tables`** (project_id `bkyztodycgvhagzcubes`, schema `public`, `verbose: true`)

Expected: as 12 tabelas listadas acima, cada uma com as colunas do DDL.

- [ ] **Step 3: `app/core/supabase_client.py`**

```python
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
```

- [ ] **Step 4: `tests/test_supabase_client.py`** (smoke test — prova que a chave/URL do `.env` estão corretas e o schema existe)

```python
from app.core.supabase_client import get_service_client


def test_service_client_can_query_tenants():
    client = get_service_client()
    response = client.table("tenants").select("id").limit(1).execute()
    assert isinstance(response.data, list)
```

- [ ] **Step 5: Preencher `.env` local** com `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY` reais (pegue no painel do projeto `bkyztodycgvhagzcubes` ou via `get_project_url`/chaves publicáveis da MCP) antes de rodar o teste.

- [ ] **Step 6: Rodar e confirmar**

Run: `pytest -v`
Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add app/core/ tests/test_supabase_client.py
git commit -m "feat: schema Supabase completo (12 tabelas + RLS) e cliente de servico

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Núcleo de autenticação (JWT + erros + fixtures de teste)

**Files:**
- Create: `app/core/errors.py`, `app/core/auth.py`, `app/deps.py`, `app/modules/__init__.py`, `app/modules/auth/__init__.py`, `app/modules/auth/router.py`, `app/modules/auth/schemas.py`, `tests/test_auth_core.py`, `tests/test_auth_router.py`
- Modify: `app/main.py` (registra exception handlers + inclui `auth.router`), `tests/conftest.py` (adiciona fixtures de tenant/usuários reais)

**Interfaces (Produces — contrato para todas as tasks de módulo seguintes):**

```python
# app/core/errors.py
class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None: ...

def register_exception_handlers(app: FastAPI) -> None: ...
```

```python
# app/core/auth.py
@dataclass
class AuthContext:
    user_id: str
    tenant_id: str | None
    role: str
    email: str

def extract_claims(payload: dict) -> AuthContext: ...  # pura, sem I/O
def decode_token(token: str) -> dict: ...               # verifica assinatura via JWKS (rede)
```

```python
# app/deps.py
async def get_current_user(authorization: str = Header(default="")) -> AuthContext: ...
def require_role(*roles: str) -> Callable[[AuthContext], AuthContext]: ...
def require_tenant(user: AuthContext = Depends(get_current_user)) -> str: ...  # tenant_id ou 400
```

```python
# tests/conftest.py — fixtures novas (session-scoped, criam/destroem dado real na Supabase)
# test_tenant: dict com {"id": ..., "slug": ...}
# atendente_token / gestor_token: str (JWT real de um usuário criado só para o teste)
# auth_headers(token): dict -> {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 1: `app/core/errors.py`**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
```

- [ ] **Step 2: Escrever o teste de `extract_claims` primeiro (TDD, função pura)**

`tests/test_auth_core.py`:

```python
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
```

- [ ] **Step 3: Rodar e confirmar que falha**

Run: `pytest tests/test_auth_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.auth'`

- [ ] **Step 4: `app/core/auth.py`**

```python
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from app.config import get_settings
from app.core.errors import AppError


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str | None
    role: str
    email: str


def extract_claims(payload: dict) -> AuthContext:
    app_metadata = payload.get("app_metadata", {})
    role = app_metadata.get("role")
    if not role:
        raise AppError(401, "invalid_token", "Token sem papel definido.")
    return AuthContext(
        user_id=payload["sub"],
        tenant_id=app_metadata.get("tenant_id"),
        role=role,
        email=payload.get("email", ""),
    )


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        jwk_client = PyJWKClient(settings.supabase_jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            options={"verify_aud": True},
        )
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "Token inválido ou expirado.") from exc
```

- [ ] **Step 5: Rodar e confirmar que passa**

Run: `pytest tests/test_auth_core.py -v`
Expected: `3 passed`

- [ ] **Step 6: `app/deps.py`**

```python
from collections.abc import Callable

from fastapi import Depends, Header

from app.core.auth import AuthContext, decode_token, extract_claims
from app.core.errors import AppError


async def get_current_user(authorization: str = Header(default="")) -> AuthContext:
    if not authorization.startswith("Bearer "):
        raise AppError(401, "missing_token", "Cabeçalho Authorization ausente ou inválido.")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    return extract_claims(payload)


def require_role(*roles: str) -> Callable[..., AuthContext]:
    def checker(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role not in roles:
            raise AppError(403, "forbidden", f"Papel '{user.role}' não tem acesso a este recurso.")
        return user

    return checker


def require_tenant(user: AuthContext = Depends(get_current_user)) -> str:
    if not user.tenant_id:
        raise AppError(400, "no_tenant", "Esta ação exige um tenant ativo na sessão.")
    return user.tenant_id
```

- [ ] **Step 7: `app/modules/auth/schemas.py`**

```python
from pydantic import BaseModel


class MeResponse(BaseModel):
    id: str
    tenant_id: str | None
    role: str
    email: str
```

- [ ] **Step 8: `app/modules/auth/router.py`**

```python
from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import get_current_user
from app.modules.auth.schemas import MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(user: AuthContext = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=user.user_id, tenant_id=user.tenant_id, role=user.role, email=user.email)
```

- [ ] **Step 9: Atualizar `app/main.py`**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 10: Fixtures reais de tenant/usuário em `tests/conftest.py`** (usadas por esta task e por todas as seguintes)

```python
import uuid

import pytest
from fastapi.testclient import TestClient

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
    sb.table("tenants").delete().eq("id", tenant["id"]).execute()


def _create_user_and_sign_in(sb, tenant_id: str, role: str) -> str:
    email = f"{role}.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br"
    password = "SenhaDeTeste123!"
    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "app_metadata": {"tenant_id": tenant_id, "role": role},
        }
    )
    user_id = created.user.id
    sb.table("user_profiles").insert(
        {"id": user_id, "tenant_id": tenant_id, "role": role, "name": f"Teste {role.title()}"}
    ).execute()
    session = sb.auth.sign_in_with_password({"email": email, "password": password})
    return session.session.access_token


@pytest.fixture(scope="session")
def atendente_token(test_tenant):
    sb = get_service_client()
    return _create_user_and_sign_in(sb, test_tenant["id"], "atendente")


@pytest.fixture(scope="session")
def gestor_token(test_tenant):
    sb = get_service_client()
    return _create_user_and_sign_in(sb, test_tenant["id"], "gestor")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 11: `tests/test_auth_router.py`** (prova a cadeia completa: JWT real emitido pela Supabase → `get_current_user` → papel/tenant corretos)

```python
from tests.conftest import auth_headers


def test_me_com_token_de_gestor(client, gestor_token, test_tenant):
    response = client.get("/api/v1/auth/me", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "gestor"
    assert body["tenant_id"] == test_tenant["id"]


def test_me_sem_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"
```

- [ ] **Step 12: Rodar a suíte completa**

Run: `pytest -v`
Expected: `7 passed` (os 2 anteriores + 3 de `test_auth_core` + 2 de `test_auth_router`)

- [ ] **Step 13: Commit**

```bash
git add app/core/errors.py app/core/auth.py app/deps.py app/modules/ app/main.py tests/
git commit -m "feat: nucleo de autenticacao JWT (JWKS), erros padronizados e fixtures de teste

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Módulo Tenants + Users + Settings

**Files:**
- Create: `app/modules/tenants/{__init__.py,router.py,schemas.py,service.py}`, `app/modules/users/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_tenants.py`, `tests/test_users.py`
- Modify: `app/main.py` (inclui os 2 novos routers)

**Interfaces:**
- Consumes: `get_current_user`, `require_role`, `require_tenant` (`app/deps.py`), `get_service_client` (`app/core/supabase_client.py`), `AppError`, fixtures `client`/`test_tenant`/`atendente_token`/`gestor_token`/`auth_headers` (`tests/conftest.py`).
- Produces: nada consumido por outro módulo de recurso (Tenants/Users são folhas na árvore de dependências).

**Comportamento:**
- `GET /tenants` (`admin_saas`): lista todas as linhas de `tenants`.
- `POST /tenants` (`admin_saas`): cria tenant + um `user_profiles`/`auth.users` gestor padrão "Gestor {name}" (compound, mesma regra do `TenantFormDialog` do frontend).
- `PATCH /tenants/{id}` (`gestor` só do próprio tenant, `admin_saas` qualquer um): atualiza `name`/`plan`.
- `PATCH /tenants/{id}/settings` (`gestor` só do próprio tenant): atualiza o jsonb `settings`.
- `POST /tenants/{id}/impersonate` (`admin_saas`): FastAPI assina um JWT próprio (HS256, mesmo formato de claims `app_metadata.{tenant_id,role}`) usando `SUPABASE_JWT_SECRET` — **decisão desta task**: para o token de impersonação ser aceito por `decode_token` (que hoje só valida ES256/RS256 via JWKS), adicionamos um segredo compartilhado extra só para esse caso. Ver Step abaixo.
- `GET /users` (`atendente`, `gestor`): lista `user_profiles` do tenant da sessão.
- `POST /users/invite` (`gestor`): cria usuário real via `sb.auth.admin.create_user` com `app_metadata` + linha em `user_profiles`.
- `PATCH /users/{id}/role` (`gestor`): atualiza o papel em `user_profiles` E em `app_metadata` do `auth.users` (via `sb.auth.admin.update_user_by_id`) — os dois têm que ficar sincronizados, senão o próximo login do usuário traria o papel antigo no JWT.

- [ ] **Step 1: `app/modules/tenants/schemas.py`**

```python
from pydantic import BaseModel


class TenantSettings(BaseModel):
    tags: list[str] = []
    loss_reasons: list[str] = []
    business_hours: str = ""


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    settings: TenantSettings


class TenantCreate(BaseModel):
    name: str
    plan: str = "starter"


class TenantUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None


class TenantSettingsUpdate(BaseModel):
    tags: list[str] | None = None
    loss_reasons: list[str] | None = None
    business_hours: str | None = None


class ImpersonateResponse(BaseModel):
    access_token: str
```

- [ ] **Step 2: `app/modules/tenants/service.py`**

```python
import re
import unicodedata
import uuid

import jwt

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def list_tenants() -> list[dict]:
    sb = get_service_client()
    return sb.table("tenants").select("*").execute().data


def create_tenant(name: str, plan: str) -> dict:
    sb = get_service_client()
    tenant = sb.table("tenants").insert({"name": name, "slug": _slugify(name), "plan": plan}).execute().data[0]

    email = f"gestor.{uuid.uuid4().hex[:8]}@{tenant['slug']}.amorimcrm.com.br"
    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
            "app_metadata": {"tenant_id": tenant["id"], "role": "gestor"},
        }
    )
    sb.table("user_profiles").insert(
        {"id": created.user.id, "tenant_id": tenant["id"], "role": "gestor", "name": f"Gestor {name}"}
    ).execute()
    return tenant


def update_tenant(tenant_id: str, requester_tenant_id: str | None, is_admin: bool, name: str | None, plan: str | None) -> dict:
    if not is_admin and requester_tenant_id != tenant_id:
        raise AppError(403, "forbidden", "Você só pode editar a própria loja.")
    patch = {k: v for k, v in {"name": name, "plan": plan}.items() if v is not None}
    if not patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    sb = get_service_client()
    return sb.table("tenants").update(patch).eq("id", tenant_id).execute().data[0]


def update_tenant_settings(tenant_id: str, requester_tenant_id: str, patch: dict) -> dict:
    if requester_tenant_id != tenant_id:
        raise AppError(403, "forbidden", "Você só pode editar a própria loja.")
    sb = get_service_client()
    current = sb.table("tenants").select("settings").eq("id", tenant_id).execute().data
    if not current:
        raise AppError(404, "not_found", "Loja não encontrada.")
    merged = {**current[0]["settings"], **{k: v for k, v in patch.items() if v is not None}}
    return sb.table("tenants").update({"settings": merged}).eq("id", tenant_id).execute().data[0]


def impersonate(tenant_id: str, admin_user_id: str) -> str:
    sb = get_service_client()
    tenant = sb.table("tenants").select("id").eq("id", tenant_id).execute().data
    if not tenant:
        raise AppError(404, "not_found", "Loja não encontrada.")
    settings = get_settings()
    payload = {
        "sub": admin_user_id,
        "email": "impersonation@amorimcrm.internal",
        "aud": "authenticated",
        "app_metadata": {"tenant_id": tenant_id, "role": "gestor"},
    }
    return jwt.encode(payload, settings.impersonation_secret, algorithm="HS256")
```

Isso exige um novo campo em `Settings` (Task 1's `config.py`, atualize agora):

```python
# adicionar em app/config.py, classe Settings
impersonation_secret: str
```

E em `.env.example`: `IMPERSONATION_SECRET=` (gerar um valor aleatório longo com `python -c "import secrets; print(secrets.token_hex(32))"` e colocar no `.env` real).

E `decode_token` (`app/core/auth.py`, Task 3) precisa aceitar esse segredo como alternativa ao JWKS — atualize a função:

```python
def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.impersonation_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError:
        pass
    try:
        jwk_client = PyJWKClient(settings.supabase_jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated", options={"verify_aud": True}
        )
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "Token inválido ou expirado.") from exc
```

- [ ] **Step 3: `app/modules/tenants/router.py`**

```python
from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role
from app.modules.tenants import service
from app.modules.tenants.schemas import (
    ImpersonateResponse,
    TenantCreate,
    TenantOut,
    TenantSettingsUpdate,
    TenantUpdate,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
def list_all(_: AuthContext = Depends(require_role("admin_saas"))):
    return service.list_tenants()


@router.post("", response_model=TenantOut)
def create(body: TenantCreate, _: AuthContext = Depends(require_role("admin_saas"))):
    return service.create_tenant(body.name, body.plan)


@router.patch("/{tenant_id}", response_model=TenantOut)
def update(tenant_id: str, body: TenantUpdate, user: AuthContext = Depends(get_current_user)):
    return service.update_tenant(tenant_id, user.tenant_id, user.role == "admin_saas", body.name, body.plan)


@router.patch("/{tenant_id}/settings", response_model=TenantOut)
def update_settings(tenant_id: str, body: TenantSettingsUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_tenant_settings(tenant_id, user.tenant_id, body.model_dump())


@router.post("/{tenant_id}/impersonate", response_model=ImpersonateResponse)
def impersonate(tenant_id: str, user: AuthContext = Depends(require_role("admin_saas"))):
    token = service.impersonate(tenant_id, user.user_id)
    return ImpersonateResponse(access_token=token)
```

- [ ] **Step 4: `tests/test_tenants.py`**

```python
from tests.conftest import auth_headers


def test_atendente_nao_lista_tenants(client, atendente_token):
    response = client.get("/api/v1/tenants", headers=auth_headers(atendente_token))
    assert response.status_code == 403


def test_gestor_atualiza_o_proprio_tenant(client, gestor_token, test_tenant):
    response = client.patch(
        f"/api/v1/tenants/{test_tenant['id']}", json={"name": "Loja Renomeada"}, headers=auth_headers(gestor_token)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Loja Renomeada"


def test_gestor_nao_atualiza_outro_tenant(client, gestor_token):
    response = client.patch(
        "/api/v1/tenants/00000000-0000-0000-0000-000000000000",
        json={"name": "Hack"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 403
```

- [ ] **Step 5: `app/modules/users/schemas.py`**

```python
from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    tenant_id: str | None
    role: str
    name: str
    avatar_color: str


class UserInvite(BaseModel):
    name: str
    email: str
    role: str


class UserRoleUpdate(BaseModel):
    role: str
```

- [ ] **Step 6: `app/modules/users/service.py`**

```python
import uuid

from app.core.supabase_client import get_service_client


def list_users(tenant_id: str) -> list[dict]:
    sb = get_service_client()
    return sb.table("user_profiles").select("*").eq("tenant_id", tenant_id).execute().data


def invite_user(tenant_id: str, name: str, email: str, role: str) -> dict:
    sb = get_service_client()
    created = sb.auth.admin.create_user(
        {
            "email": email,
            "password": uuid.uuid4().hex,
            "email_confirm": True,
            "app_metadata": {"tenant_id": tenant_id, "role": role},
        }
    )
    return (
        sb.table("user_profiles")
        .insert({"id": created.user.id, "tenant_id": tenant_id, "role": role, "name": name})
        .execute()
        .data[0]
    )


def update_role(user_id: str, role: str) -> dict:
    sb = get_service_client()
    sb.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": role}})
    return sb.table("user_profiles").update({"role": role}).eq("id", user_id).execute().data[0]
```

- [ ] **Step 7: `app/modules/users/router.py`**

```python
from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role, require_tenant
from app.modules.users import service
from app.modules.users.schemas import UserInvite, UserOut, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_all(tenant_id: str = Depends(require_tenant)):
    return service.list_users(tenant_id)


@router.post("/invite", response_model=UserOut)
def invite(body: UserInvite, user: AuthContext = Depends(require_role("gestor"))):
    return service.invite_user(user.tenant_id, body.name, body.email, body.role)


@router.patch("/{user_id}/role", response_model=UserOut)
def update_role(user_id: str, body: UserRoleUpdate, _: AuthContext = Depends(require_role("gestor"))):
    return service.update_role(user_id, body.role)
```

- [ ] **Step 8: `tests/test_users.py`**

```python
import uuid

from tests.conftest import auth_headers


def test_gestor_convida_e_lista_usuario(client, gestor_token, test_tenant):
    email = f"novo.{uuid.uuid4().hex[:8]}@teste.amorimcrm.com.br"
    invite = client.post(
        "/api/v1/users/invite",
        json={"name": "Novo Atendente", "email": email, "role": "atendente"},
        headers=auth_headers(gestor_token),
    )
    assert invite.status_code == 200

    listing = client.get("/api/v1/users", headers=auth_headers(gestor_token))
    assert any(u["name"] == "Novo Atendente" for u in listing.json())


def test_atendente_nao_convida(client, atendente_token):
    response = client.post(
        "/api/v1/users/invite",
        json={"name": "X", "email": "x@x.com", "role": "atendente"},
        headers=auth_headers(atendente_token),
    )
    assert response.status_code == 403
```

- [ ] **Step 9: Reescrever `app/main.py` por completo** (acrescenta os 2 routers desta task ao que a Task 3 criou):

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 10: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os testes anteriores + 3 de `test_tenants` + 2 de `test_users` passando.

- [ ] **Step 11: Commit**

```bash
git add app/config.py app/core/auth.py app/modules/tenants/ app/modules/users/ app/main.py tests/test_tenants.py tests/test_users.py .env.example
git commit -m "feat: modulos tenants (admin/impersonacao) e users (equipe)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Módulo Contacts

**Files:**
- Create: `app/modules/contacts/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_contacts.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `get_current_user`, `require_tenant` (`app/deps.py`), `get_service_client`, fixtures do `conftest.py`.
- Produces: nenhuma outra task de módulo importa `contacts.service` diretamente (Deals referencia `contact_id` só como string, sem acoplamento de código).

**Comportamento:** estabelece o padrão CRUD-com-filtros que os módulos seguintes (Appointments, Activities) repetem.

- [ ] **Step 1: `app/modules/contacts/schemas.py`**

```python
from pydantic import BaseModel


class Address(BaseModel):
    street: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""


class ContactOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    whatsapp: str
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    origin: str
    interests: list[str]
    tags: list[str]
    journey_status: str
    owner_id: str
    first_contact_at: str
    last_interaction_at: str


class ContactCreate(BaseModel):
    name: str
    whatsapp: str
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    origin: str
    interests: list[str] = []
    tags: list[str] = []
    owner_id: str


class ContactUpdate(BaseModel):
    name: str | None = None
    whatsapp: str | None = None
    instagram: str | None = None
    email: str | None = None
    cpf: str | None = None
    address: Address | None = None
    tags: list[str] | None = None
    owner_id: str | None = None
```

- [ ] **Step 2: `app/modules/contacts/service.py`**

```python
from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_contacts(
    tenant_id: str,
    journey_status: str | None,
    tag: str | None,
    origin: str | None,
    owner_id: str | None,
    search: str | None,
) -> list[dict]:
    sb = get_service_client()
    query = sb.table("contacts").select("*").eq("tenant_id", tenant_id)
    if journey_status:
        query = query.eq("journey_status", journey_status)
    if origin:
        query = query.eq("origin", origin)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if tag:
        query = query.contains("tags", [tag])
    if search:
        query = query.or_(f"name.ilike.%{search}%,whatsapp.ilike.%{search}%")
    return query.execute().data


def get_contact(tenant_id: str, contact_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("contacts").select("*").eq("tenant_id", tenant_id).eq("id", contact_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Cliente não encontrado.")
    return rows[0]


def create_contact(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    payload = {
        **data,
        "tenant_id": tenant_id,
        "journey_status": "lead",
        "first_contact_at": now,
        "last_interaction_at": now,
    }
    return sb.table("contacts").insert(payload).execute().data[0]


def update_contact(tenant_id: str, contact_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    rows = (
        sb.table("contacts")
        .update(clean_patch)
        .eq("tenant_id", tenant_id)
        .eq("id", contact_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Cliente não encontrado.")
    return rows[0]
```

- [ ] **Step 3: `app/modules/contacts/router.py`**

```python
from fastapi import APIRouter, Depends, Query

from app.deps import require_tenant
from app.modules.contacts import service
from app.modules.contacts.schemas import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    journey_status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
):
    return service.list_contacts(tenant_id, journey_status, tag, origin, owner_id, search)


@router.get("/{contact_id}", response_model=ContactOut)
def get(contact_id: str, tenant_id: str = Depends(require_tenant)):
    return service.get_contact(tenant_id, contact_id)


@router.post("", response_model=ContactOut)
def create(body: ContactCreate, tenant_id: str = Depends(require_tenant)):
    return service.create_contact(tenant_id, body.model_dump())


@router.patch("/{contact_id}", response_model=ContactOut)
def update(contact_id: str, body: ContactUpdate, tenant_id: str = Depends(require_tenant)):
    return service.update_contact(tenant_id, contact_id, body.model_dump())
```

- [ ] **Step 4: `tests/test_contacts.py`**

```python
from tests.conftest import auth_headers


def _create_contact(client, token, tenant_id, gestor_id, name="Cliente Teste"):
    response = client.post(
        "/api/v1/contacts",
        json={"name": name, "whatsapp": "+5511999990000", "origin": "whatsapp_direto", "owner_id": gestor_id},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    return response.json()


def test_criar_e_listar_contato(client, gestor_token, test_tenant, gestor_user_id):
    created = _create_contact(client, gestor_token, test_tenant["id"], gestor_user_id)
    assert created["journey_status"] == "lead"

    listing = client.get("/api/v1/contacts", headers=auth_headers(gestor_token))
    assert any(c["id"] == created["id"] for c in listing.json())


def test_filtro_por_journey_status(client, gestor_token, test_tenant, gestor_user_id):
    _create_contact(client, gestor_token, test_tenant["id"], gestor_user_id, name="Outro Cliente")
    response = client.get("/api/v1/contacts?journey_status=lead", headers=auth_headers(gestor_token))
    assert all(c["journey_status"] == "lead" for c in response.json())


def test_atualizar_contato_inexistente_404(client, gestor_token):
    response = client.patch(
        "/api/v1/contacts/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 404
```

Esse teste usa uma fixture nova, `gestor_user_id` — adicione em `tests/conftest.py` (mesmo arquivo da Task 3), retornando o `sub`/`id` do usuário gestor de teste:

```python
@pytest.fixture(scope="session")
def gestor_user_id(gestor_token) -> str:
    import jwt as pyjwt

    return pyjwt.decode(gestor_token, options={"verify_signature": False})["sub"]
```

- [ ] **Step 5: Reescrever `app/main.py` por completo:**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 4 novos de `test_contacts` passando.

- [ ] **Step 7: Commit**

```bash
git add app/modules/contacts/ app/main.py tests/test_contacts.py tests/conftest.py
git commit -m "feat: modulo contacts (lista com filtros, ficha, criacao, edicao)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Módulo Deals (Pipeline)

**Files:**
- Create: `app/modules/deals/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_deals.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `require_tenant`, `require_role`, `get_current_user` (`app/deps.py`); `get_service_client`; nada de `contacts.service` (cria contato via query direta na mesma transação lógica, para não acoplar módulos).

**Comportamento:** o módulo mais complexo — replica as regras do reducer do frontend (`src/lib/store.tsx`, `MOVE_DEAL`/`MARK_DEAL_LOST`/`UPDATE_DEAL_FINANCIALS`).

- [ ] **Step 1: `app/modules/deals/schemas.py`**

```python
from pydantic import BaseModel


class DealOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    title: str
    products: str
    value: float
    payment: str
    trade_in: bool
    trade_in_desc: str | None = None
    stage: str
    outcome: str
    loss_reason: str | None = None
    owner_id: str
    stage_changed_at: str
    supplier_product_id: str | None = None
    supplier_value: float | None = None
    gift_value: float | None = None


class LeadCreate(BaseModel):
    name: str
    whatsapp: str
    origin: str
    product_line: str | None = None
    value: float
    owner_id: str


class DealCreate(BaseModel):
    contact_id: str
    title: str
    products: str
    value: float
    payment: str
    trade_in: bool = False
    trade_in_desc: str | None = None
    owner_id: str


class DealUpdate(BaseModel):
    title: str | None = None
    products: str | None = None
    value: float | None = None
    payment: str | None = None


class MoveDealBody(BaseModel):
    stage: str


class MarkLostBody(BaseModel):
    reason: str


class DealFinancialsUpdate(BaseModel):
    supplier_product_id: str | None = None
    supplier_value: float
    gift_value: float
```

- [ ] **Step 2: `app/modules/deals/service.py`**

```python
from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client

PRODUCT_LINE_LABELS = {
    "iphone": "iPhone", "ipad": "iPad", "mac": "Mac", "watch": "Apple Watch",
    "airpods": "AirPods", "acessorios": "Acessórios",
}


def list_deals(tenant_id: str, stage: str | None, outcome: str | None, owner_id: str | None, contact_id: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("deals").select("*").eq("tenant_id", tenant_id)
    if stage:
        query = query.eq("stage", stage)
    if outcome:
        query = query.eq("outcome", outcome)
    if owner_id:
        query = query.eq("owner_id", owner_id)
    if contact_id:
        query = query.eq("contact_id", contact_id)
    return query.execute().data


def create_lead(tenant_id: str, name: str, whatsapp: str, origin: str, product_line: str | None, value: float, owner_id: str) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    product_label = PRODUCT_LINE_LABELS.get(product_line, "Novo negócio")

    contact = (
        sb.table("contacts")
        .insert(
            {
                "tenant_id": tenant_id, "name": name, "whatsapp": whatsapp, "origin": origin,
                "interests": [product_line] if product_line else [], "journey_status": "lead",
                "owner_id": owner_id, "first_contact_at": now, "last_interaction_at": now,
            }
        )
        .execute()
        .data[0]
    )
    deal = (
        sb.table("deals")
        .insert(
            {
                "tenant_id": tenant_id, "contact_id": contact["id"], "title": product_label, "products": product_label,
                "value": value, "payment": "pix", "stage": "novo_lead", "outcome": "aberto",
                "owner_id": owner_id, "stage_changed_at": now,
            }
        )
        .execute()
        .data[0]
    )
    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": contact["id"], "deal_id": deal["id"], "user_id": owner_id,
            "type": "mudanca_estagio", "description": f"Novo lead criado: {product_label}.",
        }
    ).execute()
    return deal


def create_deal(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    payload = {**data, "tenant_id": tenant_id, "stage": "novo_lead", "outcome": "aberto", "stage_changed_at": now}
    return sb.table("deals").insert(payload).execute().data[0]


def _get_deal(sb, tenant_id: str, deal_id: str) -> dict:
    rows = sb.table("deals").select("*").eq("tenant_id", tenant_id).eq("id", deal_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Negócio não encontrado.")
    return rows[0]


def update_deal(tenant_id: str, deal_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    _get_deal(sb, tenant_id, deal_id)
    return sb.table("deals").update(clean_patch).eq("id", deal_id).execute().data[0]


def move_deal(tenant_id: str, deal_id: str, stage: str, user_id: str) -> dict:
    sb = get_service_client()
    deal = _get_deal(sb, tenant_id, deal_id)
    if deal["stage"] == stage:
        return deal  # no-op, mesma guarda do reducer do frontend

    now = datetime.now(UTC).isoformat()
    is_win = stage == "pos_venda"
    patch = {"stage": stage, "stage_changed_at": now}
    if is_win:
        patch["outcome"] = "ganho"
    updated = sb.table("deals").update(patch).eq("id", deal_id).execute().data[0]

    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": deal["contact_id"], "deal_id": deal_id, "user_id": user_id,
            "type": "mudanca_estagio", "description": f"Deal movido para o estágio {stage}.",
        }
    ).execute()

    if is_win:
        sb.table("activities").insert(
            {
                "tenant_id": tenant_id, "contact_id": deal["contact_id"], "deal_id": deal_id, "user_id": user_id,
                "type": "venda", "description": f"Venda concluída: {deal['products']}.",
            }
        ).execute()
        won_count = (
            sb.table("deals")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("contact_id", deal["contact_id"])
            .eq("outcome", "ganho")
            .execute()
            .count
        )
        journey_status = "recorrente" if won_count >= 2 else "cliente"
        sb.table("contacts").update({"journey_status": journey_status}).eq("id", deal["contact_id"]).execute()

    return updated


def mark_lost(tenant_id: str, deal_id: str, reason: str) -> dict:
    sb = get_service_client()
    _get_deal(sb, tenant_id, deal_id)
    return sb.table("deals").update({"outcome": "perdido", "loss_reason": reason}).eq("id", deal_id).execute().data[0]


def update_financials(tenant_id: str, deal_id: str, supplier_product_id: str | None, supplier_value: float, gift_value: float) -> dict:
    sb = get_service_client()
    _get_deal(sb, tenant_id, deal_id)
    patch = {"supplier_product_id": supplier_product_id, "supplier_value": supplier_value, "gift_value": gift_value}
    return sb.table("deals").update(patch).eq("id", deal_id).execute().data[0]
```

- [ ] **Step 3: `app/modules/deals/router.py`**

```python
from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_role, require_tenant
from app.modules.deals import service
from app.modules.deals.schemas import (
    DealCreate,
    DealFinancialsUpdate,
    DealOut,
    DealUpdate,
    LeadCreate,
    MarkLostBody,
    MoveDealBody,
)

router = APIRouter(tags=["deals"])


@router.get("/deals", response_model=list[DealOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    stage: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    contact_id: str | None = Query(default=None),
):
    return service.list_deals(tenant_id, stage, outcome, owner_id, contact_id)


@router.post("/leads", response_model=DealOut)
def create_lead(body: LeadCreate, tenant_id: str = Depends(require_tenant)):
    return service.create_lead(tenant_id, body.name, body.whatsapp, body.origin, body.product_line, body.value, body.owner_id)


@router.post("/deals", response_model=DealOut)
def create(body: DealCreate, tenant_id: str = Depends(require_tenant)):
    return service.create_deal(tenant_id, body.model_dump())


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update(deal_id: str, body: DealUpdate, tenant_id: str = Depends(require_tenant)):
    return service.update_deal(tenant_id, deal_id, body.model_dump())


@router.post("/deals/{deal_id}/move", response_model=DealOut)
def move(deal_id: str, body: MoveDealBody, user: AuthContext = Depends(get_current_user)):
    return service.move_deal(user.tenant_id, deal_id, body.stage, user.user_id)


@router.post("/deals/{deal_id}/mark-lost", response_model=DealOut)
def mark_lost(deal_id: str, body: MarkLostBody, tenant_id: str = Depends(require_tenant)):
    return service.mark_lost(tenant_id, deal_id, body.reason)


@router.patch("/deals/{deal_id}/financials", response_model=DealOut)
def update_financials(deal_id: str, body: DealFinancialsUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_financials(user.tenant_id, deal_id, body.supplier_product_id, body.supplier_value, body.gift_value)
```

- [ ] **Step 4: `tests/test_deals.py`**

`owner_id` tem `references user_profiles(id)` — todo teste usa a fixture `gestor_user_id` (já criada na Task 5) como valor real, nunca uma string solta.

```python
from tests.conftest import auth_headers


def test_criar_lead_gera_contato_e_deal(client, gestor_token, gestor_user_id):
    response = client.post(
        "/api/v1/leads",
        json={
            "name": "Lead Teste", "whatsapp": "+5511988880000", "origin": "instagram_organico",
            "value": 5000, "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "novo_lead"
    assert body["outcome"] == "aberto"


def test_mover_deal_para_pos_venda_marca_ganho(client, gestor_token, gestor_user_id):
    lead = client.post(
        "/api/v1/leads",
        json={
            "name": "Lead Ganho", "whatsapp": "+5511977770000", "origin": "indicacao",
            "value": 3000, "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    ).json()

    moved = client.post(f"/api/v1/deals/{lead['id']}/move", json={"stage": "pos_venda"}, headers=auth_headers(gestor_token))
    assert moved.status_code == 200
    assert moved.json()["outcome"] == "ganho"


def test_mover_para_mesmo_estagio_e_no_op(client, gestor_token, gestor_user_id):
    lead = client.post(
        "/api/v1/leads",
        json={
            "name": "Lead Estavel", "whatsapp": "+5511966660000", "origin": "outro",
            "value": 1000, "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    ).json()
    before = lead["stage_changed_at"]

    moved = client.post(f"/api/v1/deals/{lead['id']}/move", json={"stage": "novo_lead"}, headers=auth_headers(gestor_token))
    assert moved.json()["stage_changed_at"] == before


def test_atendente_nao_edita_financeiro(client, atendente_token, gestor_token, gestor_user_id):
    lead = client.post(
        "/api/v1/leads",
        json={
            "name": "Lead Financeiro", "whatsapp": "+5511955550000", "origin": "outro",
            "value": 4000, "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    ).json()

    response = client.patch(
        f"/api/v1/deals/{lead['id']}/financials",
        json={"supplier_value": 3000, "gift_value": 100},
        headers=auth_headers(atendente_token),
    )
    assert response.status_code == 403
```

**Ordem de execução:** como `gestor_user_id` é definido na Task 5, mas a Task 6 é implementada depois, a fixture já existe em `tests/conftest.py` no momento em que este teste roda — nenhuma ação extra necessária.

- [ ] **Step 5: Reescrever `app/main.py` por completo** (`deals.router` já define `/leads` e `/deals` internamente, sem prefixo extra):

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.deals.router import router as deals_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 4 novos de `test_deals` passando.

- [ ] **Step 7: Commit**

```bash
git add app/modules/deals/ app/main.py tests/test_deals.py
git commit -m "feat: modulo deals (pipeline, mover estagio, perder, custos financeiros)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Módulo Suppliers (Fornecedores)

**Files:**
- Create: `app/modules/suppliers/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_suppliers.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `require_tenant`, `require_role`, `get_service_client`.
- Produces: nada consumido por outros módulos (Deals referencia `supplier_product_id` só como FK solta, sem import de código).

- [ ] **Step 1: `app/modules/suppliers/schemas.py`**

```python
from pydantic import BaseModel


class SupplierOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    whatsapp: str
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierCreate(BaseModel):
    name: str
    whatsapp: str
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    whatsapp: str | None = None
    contact_name: str | None = None
    email: str | None = None
    notes: str | None = None


class SupplierProductOut(BaseModel):
    id: str
    tenant_id: str
    supplier_id: str
    name: str
    current_price: float
    updated_at: str


class SupplierProductCreate(BaseModel):
    name: str
    current_price: float


class PriceUpdate(BaseModel):
    price: float


class PriceChangeOut(BaseModel):
    id: str
    supplier_product_id: str
    price: float
    changed_at: str
```

- [ ] **Step 2: `app/modules/suppliers/service.py`**

```python
from datetime import UTC, datetime

from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_suppliers(tenant_id: str, search: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("suppliers").select("*").eq("tenant_id", tenant_id)
    if search:
        query = query.ilike("name", f"%{search}%")
    return query.execute().data


def get_supplier(tenant_id: str, supplier_id: str) -> dict:
    sb = get_service_client()
    rows = sb.table("suppliers").select("*").eq("tenant_id", tenant_id).eq("id", supplier_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Fornecedor não encontrado.")
    return rows[0]


def create_supplier(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    return sb.table("suppliers").insert({**data, "tenant_id": tenant_id}).execute().data[0]


def update_supplier(tenant_id: str, supplier_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    rows = sb.table("suppliers").update(clean_patch).eq("tenant_id", tenant_id).eq("id", supplier_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Fornecedor não encontrado.")
    return rows[0]


def list_products(tenant_id: str, supplier_id: str) -> list[dict]:
    sb = get_service_client()
    return sb.table("supplier_products").select("*").eq("tenant_id", tenant_id).eq("supplier_id", supplier_id).execute().data


def create_product(tenant_id: str, supplier_id: str, name: str, current_price: float) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC).isoformat()
    return (
        sb.table("supplier_products")
        .insert({"tenant_id": tenant_id, "supplier_id": supplier_id, "name": name, "current_price": current_price, "updated_at": now})
        .execute()
        .data[0]
    )


def update_price(tenant_id: str, product_id: str, price: float) -> dict:
    sb = get_service_client()
    rows = sb.table("supplier_products").select("id").eq("tenant_id", tenant_id).eq("id", product_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Produto não encontrado.")
    now = datetime.now(UTC).isoformat()
    sb.table("supplier_price_changes").insert(
        {"tenant_id": tenant_id, "supplier_product_id": product_id, "price": price, "changed_at": now}
    ).execute()
    return (
        sb.table("supplier_products")
        .update({"current_price": price, "updated_at": now})
        .eq("id", product_id)
        .execute()
        .data[0]
    )


def price_history(tenant_id: str, product_id: str) -> list[dict]:
    sb = get_service_client()
    return (
        sb.table("supplier_price_changes")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("supplier_product_id", product_id)
        .order("changed_at", desc=True)
        .execute()
        .data
    )
```

- [ ] **Step 3: `app/modules/suppliers/router.py`**

```python
from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import require_role, require_tenant
from app.modules.suppliers import service
from app.modules.suppliers.schemas import (
    PriceChangeOut,
    PriceUpdate,
    SupplierCreate,
    SupplierOut,
    SupplierProductCreate,
    SupplierProductOut,
    SupplierUpdate,
)

router = APIRouter(tags=["suppliers"])


@router.get("/suppliers", response_model=list[SupplierOut])
def list_all(tenant_id: str = Depends(require_tenant), search: str | None = Query(default=None)):
    return service.list_suppliers(tenant_id, search)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get(supplier_id: str, tenant_id: str = Depends(require_tenant)):
    return service.get_supplier(tenant_id, supplier_id)


@router.post("/suppliers", response_model=SupplierOut)
def create(body: SupplierCreate, user: AuthContext = Depends(require_role("gestor"))):
    return service.create_supplier(user.tenant_id, body.model_dump())


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update(supplier_id: str, body: SupplierUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_supplier(user.tenant_id, supplier_id, body.model_dump())


@router.get("/suppliers/{supplier_id}/products", response_model=list[SupplierProductOut])
def list_products(supplier_id: str, tenant_id: str = Depends(require_tenant)):
    return service.list_products(tenant_id, supplier_id)


@router.post("/suppliers/{supplier_id}/products", response_model=SupplierProductOut)
def create_product(supplier_id: str, body: SupplierProductCreate, user: AuthContext = Depends(require_role("gestor"))):
    return service.create_product(user.tenant_id, supplier_id, body.name, body.current_price)


@router.patch("/supplier-products/{product_id}/price", response_model=SupplierProductOut)
def update_price(product_id: str, body: PriceUpdate, user: AuthContext = Depends(require_role("gestor"))):
    return service.update_price(user.tenant_id, product_id, body.price)


@router.get("/supplier-products/{product_id}/price-history", response_model=list[PriceChangeOut])
def get_price_history(product_id: str, tenant_id: str = Depends(require_tenant)):
    return service.price_history(tenant_id, product_id)
```

- [ ] **Step 4: `tests/test_suppliers.py`**

```python
from tests.conftest import auth_headers


def test_gestor_cria_fornecedor_produto_e_preco(client, gestor_token):
    supplier = client.post(
        "/api/v1/suppliers",
        json={"name": "Fornecedor Teste", "whatsapp": "+5511944440000"},
        headers=auth_headers(gestor_token),
    ).json()

    product = client.post(
        f"/api/v1/suppliers/{supplier['id']}/products",
        json={"name": "iPhone Teste", "current_price": 3000},
        headers=auth_headers(gestor_token),
    ).json()
    assert product["current_price"] == 3000

    updated = client.patch(
        f"/api/v1/supplier-products/{product['id']}/price", json={"price": 3200}, headers=auth_headers(gestor_token)
    )
    assert updated.json()["current_price"] == 3200

    history = client.get(f"/api/v1/supplier-products/{product['id']}/price-history", headers=auth_headers(gestor_token))
    assert len(history.json()) == 1
    assert history.json()[0]["price"] == 3200


def test_atendente_le_mas_nao_escreve(client, atendente_token, gestor_token):
    supplier = client.post(
        "/api/v1/suppliers", json={"name": "Outro Fornecedor", "whatsapp": "+5511933330000"}, headers=auth_headers(gestor_token)
    ).json()

    read = client.get("/api/v1/suppliers", headers=auth_headers(atendente_token))
    assert read.status_code == 200

    write = client.post(
        "/api/v1/suppliers", json={"name": "Não Deveria", "whatsapp": "+5511922220000"}, headers=auth_headers(atendente_token)
    )
    assert write.status_code == 403
```

- [ ] **Step 5: Reescrever `app/main.py` por completo:**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 2 novos de `test_suppliers` passando.

- [ ] **Step 7: Commit**

```bash
git add app/modules/suppliers/ app/main.py tests/test_suppliers.py
git commit -m "feat: modulo suppliers (fornecedores, produtos, historico de preco)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Módulo Conversations (Inbox) + webhook EvolutionAPI

**Files:**
- Create: `app/modules/conversations/{__init__.py,router.py,schemas.py,service.py}`, `app/webhooks/__init__.py`, `app/webhooks/evolution.py`, `tests/test_conversations.py`
- Modify: `app/main.py`, `app/config.py` (nenhum campo novo — `evolution_api_url`/`evolution_api_key`/`evolution_webhook_secret` já existem desde a Task 1)

**Interfaces:**
- Consumes: `require_tenant`, `get_current_user`, `get_service_client`.
- Produces: nada consumido por outro módulo.

- [ ] **Step 1: `app/modules/conversations/schemas.py`**

```python
from pydantic import BaseModel


class ConversationOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    assignee_id: str | None = None
    status: str
    unread: int


class ConversationCreate(BaseModel):
    contact_id: str


class AssigneeUpdate(BaseModel):
    assignee_id: str | None = None


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    direction: str
    text: str
    author_id: str | None = None
    status: str
    created_at: str


class MessageCreate(BaseModel):
    text: str
```

- [ ] **Step 2: `app/modules/conversations/service.py`**

```python
from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_conversations(tenant_id: str, assignee_id: str | None, status: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("conversations").select("*").eq("tenant_id", tenant_id)
    if assignee_id == "null":
        query = query.is_("assignee_id", "null")
    elif assignee_id:
        query = query.eq("assignee_id", assignee_id)
    if status:
        query = query.eq("status", status)
    return query.execute().data


def create_conversation(tenant_id: str, contact_id: str) -> dict:
    sb = get_service_client()
    return sb.table("conversations").insert({"tenant_id": tenant_id, "contact_id": contact_id}).execute().data[0]


def get_messages(tenant_id: str, conversation_id: str) -> list[dict]:
    sb = get_service_client()
    conv = sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("id", conversation_id).execute().data
    if not conv:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    if conv[0]["unread"] > 0:
        sb.table("conversations").update({"unread": 0}).eq("id", conversation_id).execute()
    return (
        sb.table("messages")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
        .data
    )


def _send_via_evolution(phone: str, text: str) -> None:
    settings = get_settings()
    if not settings.evolution_api_url:
        return  # ambiente sem EvolutionAPI configurada (dev/test) — envio real fica no-op
    httpx.post(
        f"{settings.evolution_api_url}/message/sendText",
        headers={"apikey": settings.evolution_api_key},
        json={"number": phone, "text": text},
        timeout=10,
    )


def send_message(tenant_id: str, conversation_id: str, text: str, author_id: str) -> dict:
    sb = get_service_client()
    conv = sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("id", conversation_id).execute().data
    if not conv:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    contact = sb.table("contacts").select("whatsapp").eq("id", conv[0]["contact_id"]).execute().data[0]

    message = (
        sb.table("messages")
        .insert({"tenant_id": tenant_id, "conversation_id": conversation_id, "direction": "out", "text": text, "author_id": author_id})
        .execute()
        .data[0]
    )
    now = datetime.now(UTC).isoformat()
    sb.table("contacts").update({"last_interaction_at": now}).eq("id", conv[0]["contact_id"]).execute()
    sb.table("activities").insert(
        {"tenant_id": tenant_id, "contact_id": conv[0]["contact_id"], "user_id": author_id, "type": "mensagem", "description": "Mensagem enviada."}
    ).execute()
    _send_via_evolution(contact["whatsapp"], text)
    return message


def update_assignee(tenant_id: str, conversation_id: str, assignee_id: str | None) -> dict:
    sb = get_service_client()
    rows = (
        sb.table("conversations")
        .update({"assignee_id": assignee_id})
        .eq("tenant_id", tenant_id)
        .eq("id", conversation_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Conversa não encontrada.")
    return rows[0]
```

- [ ] **Step 3: `app/modules/conversations/router.py`**

```python
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
```

- [ ] **Step 4: `app/webhooks/evolution.py`**

```python
import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request

from app.config import get_settings
from app.core.errors import AppError
from app.core.supabase_client import get_service_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature: str) -> None:
    settings = get_settings()
    expected = hmac.new(settings.evolution_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise AppError(401, "invalid_signature", "Assinatura do webhook inválida.")


@router.post("/evolution")
async def receive_evolution_webhook(request: Request, x_evolution_signature: str = Header(default="")):
    raw_body = await request.body()
    _verify_signature(raw_body, x_evolution_signature)
    payload = await request.json()

    instance_phone = payload["instance"]["phone"]
    from_number = payload["message"]["from"]
    text = payload["message"]["text"]

    sb = get_service_client()
    connection = sb.table("connections").select("*").eq("phone", instance_phone).execute().data
    if not connection:
        raise AppError(404, "unknown_instance", "Conexão do WhatsApp não encontrada para este número.")
    tenant_id = connection[0]["tenant_id"]

    contact = sb.table("contacts").select("*").eq("tenant_id", tenant_id).eq("whatsapp", from_number).execute().data
    if not contact:
        raise AppError(404, "unknown_contact", "Remetente não corresponde a nenhum cliente cadastrado.")
    contact = contact[0]

    conversation = (
        sb.table("conversations").select("*").eq("tenant_id", tenant_id).eq("contact_id", contact["id"]).execute().data
    )
    if conversation:
        conversation = conversation[0]
    else:
        conversation = sb.table("conversations").insert({"tenant_id": tenant_id, "contact_id": contact["id"]}).execute().data[0]

    sb.table("messages").insert(
        {"tenant_id": tenant_id, "conversation_id": conversation["id"], "direction": "in", "text": text}
    ).execute()
    sb.table("conversations").update({"unread": conversation["unread"] + 1}).eq("id", conversation["id"]).execute()
    now = datetime.now(UTC).isoformat()
    sb.table("contacts").update({"last_interaction_at": now}).eq("id", contact["id"]).execute()
    sb.table("activities").insert(
        {
            "tenant_id": tenant_id, "contact_id": contact["id"],
            "user_id": conversation.get("assignee_id") or contact["owner_id"],
            "type": "mensagem", "description": "Mensagem recebida.",
        }
    ).execute()
    return {"status": "processed"}
```

- [ ] **Step 5: `tests/test_conversations.py`**

```python
from tests.conftest import auth_headers


def test_criar_conversa_enviar_e_ler_mensagem(client, gestor_token, gestor_user_id):
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Inbox", "whatsapp": "+5511911110000", "origin": "whatsapp_direto", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    conversation = client.post("/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)).json()

    sent = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", json={"text": "Olá!"}, headers=auth_headers(gestor_token)
    )
    assert sent.status_code == 200
    assert sent.json()["direction"] == "out"

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth_headers(gestor_token))
    assert len(messages.json()) == 1


def test_atribuir_conversa(client, gestor_token, gestor_user_id):
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Atribuicao", "whatsapp": "+5511900000001", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()
    conversation = client.post("/api/v1/conversations", json={"contact_id": contact["id"]}, headers=auth_headers(gestor_token)).json()

    updated = client.patch(
        f"/api/v1/conversations/{conversation['id']}/assignee", json={"assignee_id": gestor_user_id}, headers=auth_headers(gestor_token)
    )
    assert updated.json()["assignee_id"] == gestor_user_id
```

O webhook (`app/webhooks/evolution.py`) depende de uma instância real da EvolutionAPI para ser testado ponta a ponta — cubra-o nesta task só com o teste de assinatura inválida:

```python
def test_webhook_rejeita_assinatura_invalida(client):
    response = client.post(
        "/api/v1/webhooks/evolution",
        json={"instance": {"phone": "x"}, "message": {"from": "y", "text": "z"}},
        headers={"x-evolution-signature": "assinatura-errada"},
    )
    assert response.status_code == 401
```

- [ ] **Step 6: Reescrever `app/main.py` por completo** (`conversations.router` e `webhooks.evolution.router` ambos entram com prefixo `/api/v1`; o segundo já define `/webhooks` internamente):

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.conversations.router import router as conversations_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.webhooks.evolution import router as evolution_webhook_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 7: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 3 novos de `test_conversations` passando.

- [ ] **Step 8: Commit**

```bash
git add app/modules/conversations/ app/webhooks/ app/main.py tests/test_conversations.py
git commit -m "feat: modulo conversations (inbox) e webhook de entrada da EvolutionAPI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Módulo Appointments (Agenda)

**Files:**
- Create: `app/modules/appointments/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_appointments.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `require_tenant`, `get_service_client`. Segue exatamente o padrão CRUD-com-filtros de Contacts (Task 5).

- [ ] **Step 1: `app/modules/appointments/schemas.py`**

```python
from pydantic import BaseModel


class AppointmentOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    deal_id: str | None = None
    type: str
    starts_at: str
    ends_at: str
    status: str
    owner_id: str
    note: str | None = None


class AppointmentCreate(BaseModel):
    contact_id: str
    deal_id: str | None = None
    type: str
    starts_at: str
    ends_at: str
    owner_id: str
    note: str | None = None


class AppointmentUpdate(BaseModel):
    starts_at: str | None = None
    ends_at: str | None = None
    status: str | None = None
    note: str | None = None
```

- [ ] **Step 2: `app/modules/appointments/service.py`**

```python
from app.core.errors import AppError
from app.core.supabase_client import get_service_client


def list_appointments(tenant_id: str, date_from: str | None, date_to: str | None, contact_id: str | None) -> list[dict]:
    sb = get_service_client()
    query = sb.table("appointments").select("*").eq("tenant_id", tenant_id)
    if date_from:
        query = query.gte("starts_at", date_from)
    if date_to:
        query = query.lte("starts_at", date_to)
    if contact_id:
        query = query.eq("contact_id", contact_id)
    return query.order("starts_at").execute().data


def create_appointment(tenant_id: str, data: dict) -> dict:
    sb = get_service_client()
    return sb.table("appointments").insert({**data, "tenant_id": tenant_id}).execute().data[0]


def update_appointment(tenant_id: str, appointment_id: str, patch: dict) -> dict:
    sb = get_service_client()
    clean_patch = {k: v for k, v in patch.items() if v is not None}
    if not clean_patch:
        raise AppError(400, "empty_patch", "Nenhum campo para atualizar.")
    rows = (
        sb.table("appointments")
        .update(clean_patch)
        .eq("tenant_id", tenant_id)
        .eq("id", appointment_id)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "not_found", "Agendamento não encontrado.")
    return rows[0]
```

- [ ] **Step 3: `app/modules/appointments/router.py`**

```python
from fastapi import APIRouter, Depends, Query

from app.deps import require_tenant
from app.modules.appointments import service
from app.modules.appointments.schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=list[AppointmentOut])
def list_all(
    tenant_id: str = Depends(require_tenant),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    contact_id: str | None = Query(default=None),
):
    return service.list_appointments(tenant_id, date_from, date_to, contact_id)


@router.post("", response_model=AppointmentOut)
def create(body: AppointmentCreate, tenant_id: str = Depends(require_tenant)):
    return service.create_appointment(tenant_id, body.model_dump())


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update(appointment_id: str, body: AppointmentUpdate, tenant_id: str = Depends(require_tenant)):
    return service.update_appointment(tenant_id, appointment_id, body.model_dump())
```

- [ ] **Step 4: `tests/test_appointments.py`**

```python
from tests.conftest import auth_headers


def test_criar_listar_e_concluir_agendamento(client, gestor_token, gestor_user_id):
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Agenda", "whatsapp": "+5511800000000", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    created = client.post(
        "/api/v1/appointments",
        json={
            "contact_id": contact["id"], "type": "entrega", "starts_at": "2026-08-01T10:00:00Z",
            "ends_at": "2026-08-01T10:30:00Z", "owner_id": gestor_user_id,
        },
        headers=auth_headers(gestor_token),
    )
    assert created.status_code == 200
    appointment_id = created.json()["id"]

    listing = client.get("/api/v1/appointments?from=2026-08-01T00:00:00Z&to=2026-08-01T23:59:59Z", headers=auth_headers(gestor_token))
    assert any(a["id"] == appointment_id for a in listing.json())

    concluded = client.patch(f"/api/v1/appointments/{appointment_id}", json={"status": "concluido"}, headers=auth_headers(gestor_token))
    assert concluded.json()["status"] == "concluido"
```

- [ ] **Step 5: Reescrever `app/main.py` por completo:**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.conversations.router import router as conversations_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.webhooks.evolution import router as evolution_webhook_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 1 novo de `test_appointments` passando.

- [ ] **Step 7: Commit**

```bash
git add app/modules/appointments/ app/main.py tests/test_appointments.py
git commit -m "feat: modulo appointments (agenda)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Módulo Activities (Timeline) + Connections (WhatsApp)

**Files:**
- Create: `app/modules/activities/{__init__.py,router.py,schemas.py,service.py}`, `app/modules/connections/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_activities.py`, `tests/test_connections.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `require_tenant`, `get_current_user`, `get_service_client`.

- [ ] **Step 1: `app/modules/activities/schemas.py`**

```python
from pydantic import BaseModel


class ActivityOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    deal_id: str | None = None
    user_id: str
    type: str
    description: str
    created_at: str


class ActivityCreate(BaseModel):
    contact_id: str
    deal_id: str | None = None
    type: str
    description: str
```

- [ ] **Step 2: `app/modules/activities/service.py`**

```python
from app.core.supabase_client import get_service_client


def list_activities(tenant_id: str, contact_id: str) -> list[dict]:
    sb = get_service_client()
    return (
        sb.table("activities")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("contact_id", contact_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def create_activity(tenant_id: str, user_id: str, data: dict) -> dict:
    sb = get_service_client()
    return sb.table("activities").insert({**data, "tenant_id": tenant_id, "user_id": user_id}).execute().data[0]
```

- [ ] **Step 3: `app/modules/activities/router.py`**

```python
from fastapi import APIRouter, Depends, Query

from app.core.auth import AuthContext
from app.deps import get_current_user, require_tenant
from app.modules.activities import service
from app.modules.activities.schemas import ActivityCreate, ActivityOut

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
def list_all(contact_id: str = Query(...), tenant_id: str = Depends(require_tenant)):
    return service.list_activities(tenant_id, contact_id)


@router.post("", response_model=ActivityOut)
def create(body: ActivityCreate, user: AuthContext = Depends(get_current_user)):
    return service.create_activity(user.tenant_id, user.user_id, body.model_dump())
```

- [ ] **Step 4: `tests/test_activities.py`**

```python
from tests.conftest import auth_headers


def test_criar_e_listar_activity(client, gestor_token, gestor_user_id):
    contact = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Timeline", "whatsapp": "+5511899990000", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    created = client.post(
        "/api/v1/activities",
        json={"contact_id": contact["id"], "type": "nota", "description": "Nota de teste."},
        headers=auth_headers(gestor_token),
    )
    assert created.status_code == 200

    listing = client.get(f"/api/v1/activities?contact_id={contact['id']}", headers=auth_headers(gestor_token))
    assert len(listing.json()) == 1
```

- [ ] **Step 5: `app/modules/connections/schemas.py`**

```python
from pydantic import BaseModel


class ConnectionOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    phone: str
    status: str
    connected_at: str | None = None
```

- [ ] **Step 6: `app/modules/connections/service.py`**

```python
from datetime import UTC, datetime

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
    rows = sb.table("connections").select("*").eq("tenant_id", tenant_id).eq("id", connection_id).execute().data
    if not rows:
        raise AppError(404, "not_found", "Conexão não encontrada.")
    return rows[0]


def pair(tenant_id: str, connection_id: str) -> dict:
    sb = get_service_client()
    connection = _get_connection(sb, tenant_id, connection_id)
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


def disconnect(tenant_id: str, connection_id: str) -> dict:
    sb = get_service_client()
    _get_connection(sb, tenant_id, connection_id)
    settings = get_settings()
    if settings.evolution_api_url:
        httpx.delete(
            f"{settings.evolution_api_url}/instance/logout/{connection_id}",
            headers={"apikey": settings.evolution_api_key},
            timeout=10,
        )
    return sb.table("connections").update({"status": "desconectado"}).eq("id", connection_id).execute().data[0]
```

- [ ] **Step 7: `app/modules/connections/router.py`**

```python
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
```

- [ ] **Step 8: `tests/test_connections.py`**

```python
from tests.conftest import auth_headers
from app.core.supabase_client import get_service_client


def test_atendente_ve_so_a_propria_conexao(client, gestor_token, atendente_token, test_tenant, gestor_user_id):
    import jwt as pyjwt

    atendente_id = pyjwt.decode(atendente_token, options={"verify_signature": False})["sub"]
    sb = get_service_client()
    sb.table("connections").insert({"tenant_id": test_tenant["id"], "user_id": gestor_user_id, "phone": "+5511000000001"}).execute()
    sb.table("connections").insert({"tenant_id": test_tenant["id"], "user_id": atendente_id, "phone": "+5511000000002"}).execute()

    as_atendente = client.get("/api/v1/connections", headers=auth_headers(atendente_token))
    assert len(as_atendente.json()) == 1
    assert as_atendente.json()[0]["phone"] == "+5511000000002"

    as_gestor = client.get("/api/v1/connections", headers=auth_headers(gestor_token))
    assert len(as_gestor.json()) == 2
```

- [ ] **Step 9: Reescrever `app/main.py` por completo:**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.activities.router import router as activities_router
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.connections.router import router as connections_router
from app.modules.contacts.router import router as contacts_router
from app.modules.conversations.router import router as conversations_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.webhooks.evolution import router as evolution_webhook_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 10: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 1 de `test_activities` + 1 de `test_connections` passando.

- [ ] **Step 11: Commit**

```bash
git add app/modules/activities/ app/modules/connections/ app/main.py tests/test_activities.py tests/test_connections.py
git commit -m "feat: modulos activities (timeline) e connections (whatsapp)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Módulo Dashboard

**Files:**
- Create: `app/modules/dashboard/{__init__.py,router.py,schemas.py,service.py}`, `tests/test_dashboard.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `require_role`, `get_service_client`. Replica exatamente as fórmulas de `dashboardMetrics()` do frontend (`src/lib/selectors.ts`).

- [ ] **Step 1: `app/modules/dashboard/schemas.py`**

```python
from pydantic import BaseModel


class FunnelCount(BaseModel):
    stage: str
    count: int
    value: float


class ChannelStat(BaseModel):
    origin: str
    total: int
    won: int


class LossStat(BaseModel):
    reason: str
    count: int


class DashboardMetrics(BaseModel):
    new_leads_month: int
    in_negotiation_value: float
    revenue_month: float
    revenue_prev_month: float
    conversion_rate: float
    net_profit_month: float
    funnel_counts: list[FunnelCount]
    by_channel: list[ChannelStat]
    loss_ranking: list[LossStat]
```

- [ ] **Step 2: `app/modules/dashboard/service.py`**

```python
from calendar import monthrange
from datetime import UTC, datetime

from app.core.supabase_client import get_service_client

STAGES = ["novo_lead", "em_atendimento", "negociacao", "fechamento", "pos_venda"]


def _month_bounds(reference: datetime) -> tuple[str, str]:
    start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(reference.year, reference.month)[1]
    end = reference.replace(day=last_day, hour=23, minute=59, second=59)
    return start.isoformat(), end.isoformat()


def _prev_month_reference(reference: datetime) -> datetime:
    if reference.month == 1:
        return reference.replace(year=reference.year - 1, month=12)
    return reference.replace(month=reference.month - 1)


def get_metrics(tenant_id: str) -> dict:
    sb = get_service_client()
    now = datetime.now(UTC)
    month_start, month_end = _month_bounds(now)
    prev_start, prev_end = _month_bounds(_prev_month_reference(now))

    contacts = sb.table("contacts").select("*").eq("tenant_id", tenant_id).execute().data
    deals = sb.table("deals").select("*").eq("tenant_id", tenant_id).execute().data

    new_leads_month = sum(1 for c in contacts if month_start <= c["first_contact_at"] <= month_end)

    in_negotiation_value = sum(
        d["value"] for d in deals if d["outcome"] == "aberto" and d["stage"] in ("negociacao", "fechamento")
    )

    won_deals = [d for d in deals if d["outcome"] == "ganho"]
    revenue_month = sum(d["value"] for d in won_deals if month_start <= d["stage_changed_at"] <= month_end)
    revenue_prev_month = sum(d["value"] for d in won_deals if prev_start <= d["stage_changed_at"] <= prev_end)
    net_profit_month = sum(
        d["value"] - (d.get("supplier_value") or 0) - (d.get("gift_value") or 0)
        for d in won_deals
        if month_start <= d["stage_changed_at"] <= month_end
    )

    lost_count = sum(1 for d in deals if d["outcome"] == "perdido")
    won_count = len(won_deals)
    decided = won_count + lost_count
    conversion_rate = round((won_count / decided) * 1000) / 10 if decided else 0.0

    funnel_counts = []
    for stage in STAGES:
        stage_deals = [d for d in deals if d["outcome"] != "perdido" and d["stage"] == stage]
        funnel_counts.append({"stage": stage, "count": len(stage_deals), "value": sum(d["value"] for d in stage_deals)})

    origins = sorted({c["origin"] for c in contacts})
    by_channel = []
    for origin in origins:
        channel_contacts = [c for c in contacts if c["origin"] == origin]
        channel_ids = {c["id"] for c in channel_contacts}
        won_contact_ids = {d["contact_id"] for d in won_deals if d["contact_id"] in channel_ids}
        by_channel.append({"origin": origin, "total": len(channel_contacts), "won": len(won_contact_ids)})

    loss_counts: dict[str, int] = {}
    for d in deals:
        if d["outcome"] == "perdido" and d.get("loss_reason"):
            loss_counts[d["loss_reason"]] = loss_counts.get(d["loss_reason"], 0) + 1
    loss_ranking = sorted(
        ({"reason": reason, "count": count} for reason, count in loss_counts.items()),
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "new_leads_month": new_leads_month,
        "in_negotiation_value": in_negotiation_value,
        "revenue_month": revenue_month,
        "revenue_prev_month": revenue_prev_month,
        "conversion_rate": conversion_rate,
        "net_profit_month": net_profit_month,
        "funnel_counts": funnel_counts,
        "by_channel": by_channel,
        "loss_ranking": loss_ranking,
    }
```

- [ ] **Step 3: `app/modules/dashboard/router.py`**

```python
from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role
from app.modules.dashboard import service
from app.modules.dashboard.schemas import DashboardMetrics

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(user: AuthContext = Depends(require_role("gestor"))):
    return service.get_metrics(user.tenant_id)
```

- [ ] **Step 4: `tests/test_dashboard.py`**

```python
from tests.conftest import auth_headers


def test_atendente_nao_acessa_dashboard(client, atendente_token):
    response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(atendente_token))
    assert response.status_code == 403


def test_gestor_recebe_metricas_com_todas_as_chaves(client, gestor_token):
    response = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token))
    assert response.status_code == 200
    body = response.json()
    for key in (
        "new_leads_month", "in_negotiation_value", "revenue_month", "revenue_prev_month",
        "conversion_rate", "net_profit_month", "funnel_counts", "by_channel", "loss_ranking",
    ):
        assert key in body
```

- [ ] **Step 5: Reescrever `app/main.py` por completo:**

```python
from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.activities.router import router as activities_router
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.connections.router import router as connections_router
from app.modules.contacts.router import router as contacts_router
from app.modules.conversations.router import router as conversations_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.webhooks.evolution import router as evolution_webhook_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `pytest -v`
Expected: todos os anteriores + 2 novos de `test_dashboard` passando.

- [ ] **Step 7: Commit**

```bash
git add app/modules/dashboard/ app/main.py tests/test_dashboard.py
git commit -m "feat: modulo dashboard (metricas agregadas do gestor)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Verificação final — isolamento entre tenants e papéis

**Files:**
- Create: `tests/test_cross_tenant_isolation.py`
- Modify: nenhum arquivo de produção esperado — só correções pontuais se a verificação achar algo quebrado.

**Interfaces:**
- Consumes: todas as fixtures/módulos das Tasks 1-11.

- [ ] **Step 1: `tests/test_cross_tenant_isolation.py`** — cria um SEGUNDO tenant/gestor isolado, prova que ele não enxerga nada do `test_tenant` principal:

```python
import uuid

import pytest

from app.core.supabase_client import get_service_client
from tests.conftest import _create_user_and_sign_in, auth_headers


@pytest.fixture(scope="module")
def other_tenant():
    sb = get_service_client()
    tenant = sb.table("tenants").insert({"name": "Outra Loja", "slug": f"outra-{uuid.uuid4().hex[:8]}"}).execute().data[0]
    yield tenant
    sb.table("tenants").delete().eq("id", tenant["id"]).execute()


@pytest.fixture(scope="module")
def other_gestor_token(other_tenant):
    sb = get_service_client()
    return _create_user_and_sign_in(sb, other_tenant["id"], "gestor")


def test_contatos_nao_vazam_entre_tenants(client, gestor_token, other_gestor_token, gestor_user_id):
    created = client.post(
        "/api/v1/contacts",
        json={"name": "Contato Isolado", "whatsapp": "+5511700000000", "origin": "outro", "owner_id": gestor_user_id},
        headers=auth_headers(gestor_token),
    ).json()

    from_other_tenant = client.get("/api/v1/contacts", headers=auth_headers(other_gestor_token))
    assert all(c["id"] != created["id"] for c in from_other_tenant.json())

    direct_get = client.get(f"/api/v1/contacts/{created['id']}", headers=auth_headers(other_gestor_token))
    assert direct_get.status_code == 404


def test_dashboard_nao_mistura_dados_de_outro_tenant(client, gestor_token, other_gestor_token):
    own = client.get("/api/v1/dashboard/metrics", headers=auth_headers(gestor_token)).json()
    other = client.get("/api/v1/dashboard/metrics", headers=auth_headers(other_gestor_token)).json()
    assert own != other or (own["new_leads_month"] == 0 and other["new_leads_month"] == 0)
```

- [ ] **Step 2: Rodar a suíte completa e revisar a contagem final**

Run: `pytest -v`
Expected: todos os testes das Tasks 1-11 + os 2 novos de isolamento — todos verdes. Anote a contagem final no commit.

- [ ] **Step 3: Se algo quebrar, corrigir e repetir o Step 2** antes de commitar — não commitar com testes vermelhos.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cross_tenant_isolation.py
git commit -m "test: verificacao final de isolamento entre tenants e papeis

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
