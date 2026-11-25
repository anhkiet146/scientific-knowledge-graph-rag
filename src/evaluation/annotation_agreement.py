"""Cohen's kappa for independently labeled, pre-defined common units.

This does not establish extraction span agreement or independent annotation by itself.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def cohens_kappa(a, b):
    if not a or len(a) != len(b) or any(not str(x).strip() for x in [*a,*b]):
        raise ValueError("Two nonempty aligned label vectors are required")
    n=len(a);ca,cb=Counter(a),Counter(b)
    observed=sum(x==y for x,y in zip(a,b))/n
    expected=sum(ca[label]*cb[label] for label in set(ca)|set(cb))/n**2
    return {"n":n,"observed_agreement":observed,"expected_agreement":expected,
            "cohens_kappa":(observed-expected)/(1-expected) if expected<1 else None}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels",type=Path)
    args=parser.parse_args()
    with args.labels.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    ids=[r["item_id"] for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate annotation unit IDs")
    print(json.dumps(cohens_kappa([r["annotator_a"] for r in rows],[r["annotator_b"] for r in rows]),indent=2))
