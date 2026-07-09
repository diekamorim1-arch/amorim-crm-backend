import pytest
from pydantic import ValidationError

from app.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "supabase_url": "https://example.supabase.co",
        "supabase_service_role_key": "key",
        "supabase_anon_key": "anon",
        "environment": "development",
        "evolution_webhook_secret": "",
    }
    return Settings(**{**base, **overrides})


def test_rejeita_webhook_secret_vazio_fora_do_ambiente_de_desenvolvimento():
    with pytest.raises(ValidationError):
        _settings(environment="production", evolution_webhook_secret="")


def test_aceita_webhook_secret_vazio_em_desenvolvimento():
    settings = _settings(environment="development", evolution_webhook_secret="")
    assert settings.evolution_webhook_secret == ""


def test_aceita_producao_com_secret_configurado():
    settings = _settings(environment="production", evolution_webhook_secret="um-segredo-forte")
    assert settings.evolution_webhook_secret == "um-segredo-forte"
