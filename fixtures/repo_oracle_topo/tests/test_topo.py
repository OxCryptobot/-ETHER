import pytest
from topo import topo_sort


def test_simple_chain():
    order = topo_sort([("a", "b"), ("b", "c")])
    assert order.index("a") < order.index("b") < order.index("c")


def test_diamond():
    order = topo_sort([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert order[0] == "a"
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_disconnected():
    order = topo_sort([("a", "b"), ("c", "d")])
    assert set(order) == {"a", "b", "c", "d"}
    assert order.index("a") < order.index("b")
    assert order.index("c") < order.index("d")


def test_single_edge():
    order = topo_sort([("x", "y")])
    assert order.index("x") < order.index("y")


def test_cycle_raises():
    with pytest.raises(ValueError):
        topo_sort([("a", "b"), ("b", "a")])


def test_self_loop_raises():
    with pytest.raises(ValueError):
        topo_sort([("a", "a")])


def test_longer_cycle_raises():
    with pytest.raises(ValueError):
        topo_sort([("a", "b"), ("b", "c"), ("c", "a")])
