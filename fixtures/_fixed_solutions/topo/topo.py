from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Set


def topo_sort(edges: List[tuple]) -> List[str]:
    nodes: Set[str] = set()
    for a, b in edges:
        nodes.add(a)
        nodes.add(b)

    indeg: Dict[str, int] = {n: 0 for n in nodes}
    adj: Dict[str, List[str]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        indeg[b] += 1

    q = deque([n for n in nodes if indeg[n] == 0])
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(nodes):
        raise ValueError("cycle detected")
    return out
