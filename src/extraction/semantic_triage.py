"""Advisory triage only: lexical checks do not prove semantic correctness."""
import argparse, json, re, unicodedata
from collections import defaultdict
from pathlib import Path

def alias_key(name):
    # Conservative candidate grouping; never automatically merge records.
    return re.sub(r"[\s\-‐‑–—]+", "", unicodedata.normalize("NFKC",name).casefold())

def audit(payload):
    data=payload.get("extraction_result",payload)
    issues=[];groups=defaultdict(list)
    entities=data.get("entities",[])
    suspect=set()
    for i,e in enumerate(entities):
        identifier=e.get("id","");name=e.get("name",identifier);typ=e.get("type")
        groups[(typ,alias_key(name))].append(identifier)
        if typ=="Dataset" and re.search(r"\b(escherichia|klebsiella|bacillus|strain|tissue|specimen)\b",name,re.I):
            issues.append({"kind":"entity","index":i,"id":name,"reason":"possible_biological_object_as_dataset","action":"human_review"});suspect.add(identifier)
        if typ=="Metric" and not re.search(r"(?<![A-Za-z])\d",name+" "+e.get("description","")):
            issues.append({"kind":"entity","index":i,"id":name,"reason":"metric_without_numeric_value","action":"human_review"})
    for (typ,key),names in groups.items():
        if len(names)>1:issues.append({"kind":"alias_candidate","type":typ,"ids":names,"action":"human_review_no_auto_merge"})
    for i,r in enumerate(data.get("relations",[])):
        if r.get("type")=="EVALUATED_ON" and r.get("target") in suspect:
            issues.append({"kind":"relation","index":i,"reason":"target_requires_dataset_review","action":"human_review"})
    return {"semantic_correctness":"not_established","checks":"advisory_incomplete_lexical_triage", "issues":issues}
