from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import model_validator

load_dotenv()


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_webhook_secret: str = ""
    environment: str = "development"

    @model_validator(mode="after")
    def _require_webhook_secret_outside_development(self) -> "Settings":
        # Sem isso, um deploy em produção sem EVOLUTION_WEBHOOK_SECRET configurado
        # faria _verify_signature calcular o HMAC com chave vazia — um valor que
        # qualquer atacante reproduz, aceitando webhooks forjados silenciosamente.
        # Falhar já na carga das settings (import de app.main) impede o serviço de
        # subir nesse estado, em vez de só falhar (ou pior, aceitar) na 1ª chamada.
        if self.environment != "development" and not self.evolution_webhook_secret:
            raise ValueError(
                "EVOLUTION_WEBHOOK_SECRET não pode ficar vazio fora do ambiente de "
                "desenvolvimento (ENVIRONMENT != 'development')."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
