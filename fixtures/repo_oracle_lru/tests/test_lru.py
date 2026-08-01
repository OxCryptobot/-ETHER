import pytest
from lru import LRUCache


def test_basic_put_get():
    c = LRUCache(2)
    c.put("a", 1)
    assert c.get("a") == 1


def test_miss_returns_none():
    c = LRUCache(2)
    assert c.get("missing") is None


def test_evicts_least_recently_used():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_get_refreshes_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    c.put("c", 3)
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3


def test_update_existing_no_evict():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 10)
    assert c.get("a") == 10
    assert c.get("b") == 2


def test_capacity_one():
    c = LRUCache(1)
    c.put("x", 1)
    c.put("y", 2)
    assert c.get("x") is None
    assert c.get("y") == 2


def test_bad_capacity():
    with pytest.raises(ValueError):
        LRUCache(0)
