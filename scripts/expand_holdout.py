#!/usr/bin/env python3
"""Expand holdout quiz toward 50 tasks (idempotent append)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT = ROOT / "memory" / "quizzes" / "holdout_v1.json"
IDS = ROOT / "memory" / "quizzes" / "holdout_ids.json"

EXTRA = [
    {"id": "h21", "objective": "Write only Python: def product(xs):\n    r=1\n    for x in xs: r*=x\n    return r\nassert product([2,3,4])==24\nprint(product([2,3,4]))"},
    {"id": "h22", "objective": "Write only Python: def drop_while(xs, pred):\n    i=0\n    while i<len(xs) and pred(xs[i]): i+=1\n    return xs[i:]\nassert drop_while([0,0,1,2], lambda x:x==0)==[1,2]\nprint(drop_while([0,0,1,2], lambda x:x==0))"},
    {"id": "h23", "objective": "Write only Python: def chunk(xs,n):\n    return [xs[i:i+n] for i in range(0,len(xs),n)]\nassert chunk([1,2,3,4],2)==[[1,2],[3,4]]\nprint(chunk([1,2,3,4],2))"},
    {"id": "h24", "objective": "Write only Python: def flatten_dict(d, prefix=''):\n    out={}\n    for k,v in d.items():\n        key=f'{prefix}.{k}' if prefix else k\n        if isinstance(v, dict): out.update(flatten_dict(v, key))\n        else: out[key]=v\n    return out\nassert flatten_dict({'a':{'b':1}})['a.b']==1\nprint(flatten_dict({'a':{'b':1}}))"},
    {"id": "h25", "objective": "Write only Python: def levenshtein(a,b):\n    dp=list(range(len(b)+1))\n    for i,ca in enumerate(a,1):\n        prev=dp[:]; dp[0]=i\n        for j,cb in enumerate(b,1):\n            dp[j]=min(prev[j]+1, dp[j-1]+1, prev[j-1]+(ca!=cb))\n    return dp[-1]\nassert levenshtein('kitten','sitting')==3\nprint(levenshtein('kitten','sitting'))"},
    {"id": "h26", "objective": "Write only Python: def powerset_size(n):\n    return 2**n\nassert powerset_size(3)==8\nprint(powerset_size(3))"},
    {"id": "h27", "objective": "Write only Python: def rle_decode(pairs):\n    return ''.join(ch*n for ch,n in pairs)\nassert rle_decode([('a',2),('b',1)])=='aab'\nprint(rle_decode([('a',2),('b',1)]))"},
    {"id": "h28", "objective": "Write only Python: def sliding_max(xs,k):\n    return [max(xs[i:i+k]) for i in range(len(xs)-k+1)]\nassert sliding_max([1,3,2,5],2)==[3,3,5]\nprint(sliding_max([1,3,2,5],2))"},
    {"id": "h29", "objective": "Write only Python: def invert_map(d):\n    return {v:k for k,v in d.items()}\nassert invert_map({'a':1})[1]=='a'\nprint(invert_map({'a':1}))"},
    {"id": "h30", "objective": "Write only Python: def take(xs,n):\n    return xs[:n]\nassert take([1,2,3],2)==[1,2]\nprint(take([1,2,3],2))"},
    {"id": "h31", "objective": "Write only Python: def zip_to_dict(keys, vals):\n    return dict(zip(keys, vals))\nassert zip_to_dict(['a','b'],[1,2])=={'a':1,'b':2}\nprint(zip_to_dict(['a','b'],[1,2]))"},
    {"id": "h32", "objective": "Write only Python: def is_sorted(xs):\n    return all(xs[i]<=xs[i+1] for i in range(len(xs)-1))\nassert is_sorted([1,2,2,3]) and not is_sorted([2,1])\nprint(is_sorted([1,2,3]))"},
    {"id": "h33", "objective": "Write only Python: def mean(xs):\n    return sum(xs)/len(xs) if xs else 0\nassert mean([2,4])==3\nprint(mean([2,4]))"},
    {"id": "h34", "objective": "Write only Python: def clamp_list(xs,lo,hi):\n    return [max(lo,min(hi,x)) for x in xs]\nassert clamp_list([0,5,10],1,8)==[1,5,8]\nprint(clamp_list([0,5,10],1,8))"},
    {"id": "h35", "objective": "Write only Python: def count_if(xs, pred):\n    return sum(1 for x in xs if pred(x))\nassert count_if([1,2,3,4], lambda x:x%2==0)==2\nprint(count_if([1,2,3,4], lambda x:x%2==0))"},
    {"id": "h36", "objective": "Write only Python: def repeat(x,n):\n    return [x]*n\nassert repeat('z',3)==['z','z','z']\nprint(repeat('z',3))"},
    {"id": "h37", "objective": "Write only Python: def head_tail(xs):\n    return (xs[0], xs[1:]) if xs else (None, [])\nassert head_tail([1,2,3])==(1,[2,3])\nprint(head_tail([1,2,3]))"},
    {"id": "h38", "objective": "Write only Python: def merge_unique(a,b):\n    out=[]; seen=set()\n    for x in list(a)+list(b):\n        if x not in seen:\n            seen.add(x); out.append(x)\n    return out\nassert merge_unique([1,2],[2,3])==[1,2,3]\nprint(merge_unique([1,2],[2,3]))"},
    {"id": "h39", "objective": "Write only Python: def index_map(xs):\n    return {x:i for i,x in enumerate(xs)}\nassert index_map(['a','b'])['b']==1\nprint(index_map(['a','b']))"},
    {"id": "h40", "objective": "Write only Python: def safe_div(a,b):\n    return a/b if b else None\nassert safe_div(6,3)==2 and safe_div(1,0) is None\nprint(safe_div(6,3))"},
    {"id": "h41", "objective": "Write only Python: def digits_sum(n):\n    return sum(int(c) for c in str(abs(n)))\nassert digits_sum(123)==6\nassert digits_sum(-45)==9\nprint(digits_sum(123))"},
    {"id": "h42", "objective": "Write only Python: def unique_preserve(xs):\n    seen=set(); out=[]\n    for x in xs:\n        if x not in seen:\n            seen.add(x); out.append(x)\n    return out\nassert unique_preserve([1,2,1,3])==[1,2,3]\nprint(unique_preserve([1,2,1,3]))"},
    {"id": "h43", "objective": "Write only Python: def rotate_left(xs,k):\n    if not xs: return []\n    k=k%len(xs)\n    return xs[k:]+xs[:k]\nassert rotate_left([1,2,3,4],1)==[2,3,4,1]\nprint(rotate_left([1,2,3,4],1))"},
    {"id": "h44", "objective": "Write only Python: def is_palindrome(s):\n    t=''.join(c.lower() for c in s if c.isalnum())\n    return t==t[::-1]\nassert is_palindrome('A man a plan a canal Panama')\nassert not is_palindrome('hello')\nprint(is_palindrome('racecar'))"},
    {"id": "h45", "objective": "Write only Python: def gcd(a,b):\n    while b: a,b=b,a%b\n    return abs(a)\nassert gcd(12,18)==6\nassert gcd(7,3)==1\nprint(gcd(12,18))"},
    {"id": "h46", "objective": "Write only Python: def flatten_once(xs):\n    out=[]\n    for x in xs:\n        if isinstance(x, list): out.extend(x)\n        else: out.append(x)\n    return out\nassert flatten_once([1,[2,3],4])==[1,2,3,4]\nprint(flatten_once([1,[2,3],4]))"},
    {"id": "h47", "objective": "Write only Python: def mode(xs):\n    from collections import Counter\n    if not xs: return None\n    return Counter(xs).most_common(1)[0][0]\nassert mode([1,2,2,3])==2\nprint(mode([1,2,2,3]))"},
    {"id": "h48", "objective": "Write only Python: def binary_search(xs, target):\n    lo,hi=0,len(xs)-1\n    while lo<=hi:\n        mid=(lo+hi)//2\n        if xs[mid]==target: return mid\n        if xs[mid]<target: lo=mid+1\n        else: hi=mid-1\n    return -1\nassert binary_search([1,3,5,7],5)==2\nassert binary_search([1,3,5,7],2)==-1\nprint(binary_search([1,3,5,7],5))"},
    {"id": "h49", "objective": "Write only Python: def transpose(m):\n    return [list(row) for row in zip(*m)] if m else []\nassert transpose([[1,2],[3,4]])==[[1,3],[2,4]]\nprint(transpose([[1,2],[3,4]]))"},
    {"id": "h50", "objective": "Write only Python: def running_sum(xs):\n    out=[]; s=0\n    for x in xs:\n        s+=x; out.append(s)\n    return out\nassert running_sum([1,2,3])==[1,3,6]\nprint(running_sum([1,2,3]))"},
]


def main() -> int:
    HOLDOUT.parent.mkdir(parents=True, exist_ok=True)
    if HOLDOUT.exists():
        data = json.loads(HOLDOUT.read_text(encoding="utf-8"))
    else:
        data = {"tasks": []}
    tasks = list(data.get("tasks") or [])
    have = {t.get("id") for t in tasks}
    for t in EXTRA:
        if t["id"] not in have:
            tasks.append(t)
            have.add(t["id"])
    data["tasks"] = tasks
    HOLDOUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    IDS.write_text(json.dumps({"ids": sorted(have)}, indent=2), encoding="utf-8")
    print(json.dumps({"n": len(tasks), "ids": len(have)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
