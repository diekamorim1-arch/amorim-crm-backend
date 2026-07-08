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
    evolution_webhook_secret: str = ""
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
