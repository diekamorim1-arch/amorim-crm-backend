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
