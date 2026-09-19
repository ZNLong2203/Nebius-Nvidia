import time

from cache import TTLCache


def test_stores_and_returns_a_value():
    c = TTLCache(maxsize=2, ttl=10)
    c.set("a", 1)
    assert c.get("a") == 1


def test_evicts_the_oldest_entry_when_full():
    c = TTLCache(maxsize=2, ttl=10)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert len(c) == 2
    assert c.get("a") is None
    assert c.get("c") == 3


def test_an_expired_entry_is_not_returned():
    c = TTLCache(maxsize=4, ttl=1)
    c.set("a", 1)
    assert c.get("a", now=time.monotonic() + 5) is None


def test_expired_entries_are_dropped_from_the_cache():
    """An expired entry must not keep occupying a slot."""
    c = TTLCache(maxsize=2, ttl=1)
    c.set("a", 1)
    c.get("a", now=time.monotonic() + 5)
    assert len(c) == 0


def test_reading_an_entry_keeps_it_alive_for_eviction():
    """A recently read entry is not the one evicted when the cache fills."""
    c = TTLCache(maxsize=2, ttl=100)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")
    c.set("c", 3)
    assert c.get("a") == 1
    assert c.get("b") is None
