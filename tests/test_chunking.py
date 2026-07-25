from core.chunking import chunk_python_source


def test_chunks_functions():
    src = '''
"""mod"""

def alpha():
    return 1

def beta(x):
    return x * 2
'''
    chunks = chunk_python_source(src, path="demo.py")
    assert len(chunks) >= 2
    symbols = {c["metadata"].get("symbol") for c in chunks}
    assert "alpha" in symbols
    assert "beta" in symbols


def test_empty():
    assert chunk_python_source("") == []
