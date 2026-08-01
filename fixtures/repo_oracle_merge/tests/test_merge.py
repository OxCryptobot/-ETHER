from merge import merge_sorted


def test_basic():
    assert merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]


def test_duplicates():
    assert merge_sorted([1, 2, 2], [2, 3]) == [1, 2, 2, 2, 3]


def test_empty_left():
    b = [1, 2]
    out = merge_sorted([], b)
    assert out == [1, 2]
    assert out is not b


def test_empty_right():
    a = [1, 2]
    out = merge_sorted(a, [])
    assert out == [1, 2]
    assert out is not a


def test_both_empty():
    assert merge_sorted([], []) == []


def test_longer_left():
    assert merge_sorted([1, 2, 3, 4, 5], [0]) == [0, 1, 2, 3, 4, 5]


def test_longer_right():
    assert merge_sorted([0], [1, 2, 3, 4, 5]) == [0, 1, 2, 3, 4, 5]


def test_negative():
    assert merge_sorted([-5, -1, 0], [-3, 2]) == [-5, -3, -1, 0, 2]
