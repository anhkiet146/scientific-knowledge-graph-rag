"""Repair a mechanically detectable type/target field swap, retaining a full audit.

No new relation is inferred: the old target must already be a valid relation label
and the old type must already name an entity in the same extraction document.
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src/normalization"))
from normalize_entities import extraction_payload

ALLOWED={"BELONGS_TO","USED_FOR","EVALUATED_ON","ACHIEVED","AFFILIATED_WITH"}


def repair_payload(payload):
    names=Counter(e.get("id",e.get("name","")) for e in payload.get("entities",[]))
    changes=[];unresolved=[]
    for index,relation in enumerate(payload.get("relations",[]),1):
        if relation.get("type") in ALLOWED:continue
        before=dict(relation)
        if (relation.get("target") in ALLOWED and names[relation.get("type")]>0
                and names[relation.get("source")]>0):
            relation["type"],relation["target"]=relation["target"],relation["type"]
            changes.append({"relation_index":index,"before":before,"after":dict(relation),
                            "rule":"known relation in old target; old type and source already name document entities"})
        else:unresolved.append({"relation_index":index,"relation":before})
    return changes,unresolved


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--audit",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):raise ValueError("Use an empty output directory")
    args.output.mkdir(parents=True,exist_ok=True)
    report={"schema_scope":"five operational labels of the released extraction pipeline; manuscript label mapping still needs reconciliation",
            "repairs":[],"unresolved":[],"documents_processed":0}
    for path in sorted(args.input.glob("*.json")):
        if path.name.startswith("_"):continue
        document=json.loads(path.read_text(encoding="utf-8-sig"));payload=extraction_payload(document)
        changes,unresolved=repair_payload(payload)
        report["repairs"].extend({"file":path.name,**r} for r in changes)
        report["unresolved"].extend({"file":path.name,**r} for r in unresolved)
        if changes:
            document["extraction_result"]=payload
            (args.output/path.name).write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding="utf-8")
        else:shutil.copy2(path,args.output/path.name)
        report["documents_processed"]+=1
    args.audit.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"documents":report["documents_processed"],"field_swaps_repaired":len(report["repairs"]),
                      "unknown_relations_unresolved":len(report["unresolved"])}))
