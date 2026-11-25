"""Reviewed, typed graph import. One atomic transaction per paper; no live writes on import."""
import copy
import argparse
import logging
import os
import sys
from pathlib import Path
import json
from neo4j import GraphDatabase

try:
    from ..extraction.graph_policy import require_graph_review
    from ..extraction.workflow_io import read_json,canonical_hash
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"extraction"))
    from graph_policy import require_graph_review
    from workflow_io import read_json,canonical_hash

logger=logging.getLogger(__name__)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'retrieval'))
from graph_connection import graph_session
INPUT_FOLDER=os.getenv("GRAPH_JSON_DIR",str(Path(__file__).resolve().parents[2]/"data/graph_json_exact_revision"))
NEO4J_URI=os.getenv("NEO4J_URI","bolt://localhost:7687")
NEO4J_USER=os.getenv("NEO4J_USER","neo4j")
NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD","")


def _run(tx,query,**parameters):
    # Consume lazy results inside the transaction so delayed failures roll back.
    tx.run(query,**parameters).consume()


def _write_paper(tx,data):
    payload=data["extraction_result"];paper=data["filename"]
    _run(tx,"""MERGE (p:Paper {filename:$filename})
        SET p.title=$title,p.name=$title,p.abstract=$abstract,p.source_sha256=$source_sha256,
            p.review_json=$review_json,p.source_issues_json=$issues_json""",
        filename=paper,title=data.get("paper_title",data.get("title",paper)),
        abstract=data.get("abstract",""),source_sha256=data["source_sha256"],
        review_json=json.dumps(data['review'],ensure_ascii=False,sort_keys=True),
        issues_json=json.dumps(data.get('blocking_issues',[]),ensure_ascii=False,sort_keys=True))
    identities={}
    for entity in payload["entities"]:
        label=entity["type"];identifier=entity["id"];name=entity.get("name",identifier)
        scoped=label=='Metric' or entity.get('identity_scope')=='paper'
        prop='record_key' if scoped else 'name'
        key=canonical_hash({'paper':paper,'type':label,'id':identifier,'measurement':entity.get('measurement')}) if scoped else name
        identities[identifier]=(label,prop,key)
        query=f"MERGE (e:`{label}` {{{prop}:$entity_key}}) ON CREATE SET e.description=$description SET e.name=$name"
        parameters={'entity_key':key,'name':name,'description':entity.get('description','')}
        if label=='Metric':
            query+=', e.measurement_json=$measurement_json'
            parameters['measurement_json']=json.dumps(entity['measurement'],ensure_ascii=False,sort_keys=True)
        _run(tx,query,**parameters)
        record=json.dumps({"paper":paper,"evidence":entity["evidence"],"measurement":entity.get("measurement")},ensure_ascii=False,sort_keys=True)
        _run(tx,f"""MATCH (p:Paper {{filename:$paper}})
            MATCH (e:`{label}` {{{prop}:$entity_key}}) MERGE (p)-[r:MENTIONS]->(e)
            SET r.evidence_records=CASE WHEN $record IN coalesce(r.evidence_records,[])
            THEN r.evidence_records ELSE coalesce(r.evidence_records,[])+[$record] END""",
            paper=paper,entity_key=key,record=record)
    for relation in payload["relations"]:
        src,tgt,kind=relation["source"],relation["target"],relation["type"]
        src_type,src_prop,src_key=identities[src];tgt_type,tgt_prop,tgt_key=identities[tgt]
        record=json.dumps({"paper":paper,"evidence":relation["evidence"]},ensure_ascii=False,sort_keys=True)
        _run(tx,f"""MATCH (a:`{src_type}` {{{src_prop}:$src}})
            MATCH (b:`{tgt_type}` {{{tgt_prop}:$tgt}}) MERGE (a)-[r:{kind}]->(b)
            SET r.source_papers=CASE WHEN $paper IN coalesce(r.source_papers,[])
                THEN r.source_papers ELSE coalesce(r.source_papers,[])+[$paper] END,
                r.evidence_records=CASE WHEN $record IN coalesce(r.evidence_records,[])
                THEN r.evidence_records ELSE coalesce(r.evidence_records,[])+[$record] END""",
            src=src_key,tgt=tgt_key,paper=paper,record=record)
    return {"entities_saved":len(payload["entities"]),"relations_saved":len(payload["relations"])}


class KnowledgeGraphBuilder:
    def __init__(self,uri,user,password):
        self.driver=GraphDatabase.driver(uri,auth=(user,password))

    def close(self):self.driver.close()

    def load_paper_data(self,data):
        frozen=copy.deepcopy(data)
        require_graph_review(frozen)  # Complete validation before any write.
        with graph_session(self.driver) as session:
            return session.execute_write(_write_paper,frozen)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=Path(INPUT_FOLDER))
    args=parser.parse_args()
    files=sorted(p for p in args.input.glob("*.json") if not p.name.startswith("_"))
    if not files:raise ValueError("No input papers")
    documents=[read_json(p) for p in files]
    for data in documents:require_graph_review(data)
    if not NEO4J_PASSWORD:raise ValueError("Set NEO4J_PASSWORD before graph import")
    builder=KnowledgeGraphBuilder(NEO4J_URI,NEO4J_USER,NEO4J_PASSWORD)
    try:
        for document in documents:builder.load_paper_data(document)
    finally:builder.close()
    print(f"Imported {len(documents)} reviewed papers; each paper committed atomically")


if __name__=="__main__":main()
