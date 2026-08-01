from intervals import merge_intervals


def test_empty():
    assert merge_intervals([]) == []


def test_single():
    assert merge_intervals([(1, 3)]) == [(1, 3)]


def test_no_overlap():
    assert merge_intervals([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]


def test_overlap():
    assert merge_intervals([(1, 3), (2, 5)]) == [(1, 5)]


def test_touching():
    assert merge_intervals([(1, 2), (2, 3)]) == [(1, 3)]


def test_unsorted():
    assert merge_intervals([(5, 7), (1, 3), (2, 4)]) == [(1, 4), (5, 7)]


def test_contained():
    assert merge_intervals([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]


def test_chain():
    assert merge_intervals([(1, 2), (2, 3), (3, 4)]) == [(1, 4)]
