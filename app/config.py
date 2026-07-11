from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    # URL pública do nosso próprio webhook (POST /api/v1/webhooks/evolution),
    # que passamos pra Evolution configurar via POST /webhook/set/{instance}
    # em pair() — a Evolution API v2.1.1 não anexa webhook a uma instância
    # nova só com as env vars WEBHOOK_GLOBAL_* do container (confirmado
    # testando ao vivo), precisa desse passo explícito por instância. Vazio
    # = pair() pula essa chamada (QR/pareamento continuam funcionando, só não
    # há atualização automática de status nem recebimento de mensagens).
    evolution_webhook_url: str = ""
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
