"""
Fixtures globais compartilhadas entre todos os testes do projeto.
"""
import pytest
from django.core.cache import cache


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
