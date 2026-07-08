# Amorim CRM Backend

API FastAPI que substitui o localStorage do protótipo frontend por persistência real na Supabase.

## Rodando localmente

1. `python -m venv .venv && source .venv/Scripts/activate`
2. `pip install -r requirements.txt`
3. Copiar `.env.example` para `.env` e preencher as chaves da Supabase
4. `uvicorn app.main:app --reload`
5. `pytest -v` para rodar a suíte (a partir da Task 3, os testes usam o projeto Supabase real e criam/limpam um tenant de teste)
