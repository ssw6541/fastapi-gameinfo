import pytest

from app import cache


@pytest.fixture(autouse=True)
def _clear_mem_cache():
    cache._mem.clear()
    yield
