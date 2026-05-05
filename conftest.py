"""
Fixtures globais compartilhadas entre todos os testes do projeto.
"""
import pytest
from django.core.cache import cache


class _ThrottleRatesProxy:
    """
    Proxy lazy para ScopedRateThrottle.THROTTLE_RATES.
    Delega __getitem__ ao api_settings em tempo de execução, garantindo que
    override_settings funcione corretamente — sem este proxy, THROTTLE_RATES
    é avaliado no import da classe e fica stale durante testes com override.
    """
    def __getitem__(self, key):
        from rest_framework.settings import api_settings
        return api_settings.DEFAULT_THROTTLE_RATES[key]

    def get(self, key, default=None):
        from rest_framework.settings import api_settings
        return api_settings.DEFAULT_THROTTLE_RATES.get(key, default)


def pytest_configure(config):
    """Instala o proxy de rates no startup do pytest, antes de qualquer import de test."""
    from rest_framework.throttling import ScopedRateThrottle
    ScopedRateThrottle.THROTTLE_RATES = _ThrottleRatesProxy()


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """
    Limpa o cache do Django antes e depois de cada teste.
    Necessário porque o DRF throttle usa cache por user_id,
    e os IDs de banco se repetem após rollback de transação.
    """
    cache.clear()
    yield
    cache.clear()
