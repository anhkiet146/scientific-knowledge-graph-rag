"""Import an experimental snapshot into a new, explicitly isolated database."""
import argparse
import ast
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/extraction'))
from workflow_io import atomic_json, file_hash


def credentials(path):
    values = {}
    for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {'NEO4J_USER', 'NEO4J_PASSWORD'}:
                    value = node.value
                    if isinstance(value, ast.Call) and len(value.args) >= 2:
                        value = value.args[1]
                    values[target.id] = ast.literal_eval(value)
    return os.getenv('NEO4J_USER', values.get('NEO4J_USER', 'neo4j')), os.getenv('NEO4J_PASSWORD', values.get('NEO4J_PASSWORD', ''))


def load_plan(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['target_database'] != 'graphrag-review-482' or manifest['live_database_allowed'] is not False:
        raise ValueError('Experimental database isolation required')
    if file_hash(folder / 'records.json') != manifest['records_sha256']:
        raise ValueError('Snapshot records modified')
    records = json.loads((folder / 'records.json').read_text(encoding='utf-8'))
    if {k: len(v) for k, v in records.items()} != manifest['counts']:
        raise ValueError('Snapshot counts mismatch')
    for row in records['entities']:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', row['label']):
            raise ValueError('Invalid label')
    for row in records['relations']:
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', row['type']):
            raise ValueError('Invalid relationship type')
    return manifest, records


def populate(tx, records, digest):
    tx.run('CREATE (:Experiment {id:$id, status:"experimental_not_independently_validated"})', id=digest).consume()
    tx.run('UNWIND $rows AS row CREATE (p:Paper) SET p = row, p.id = row.key, p.name = row.title', rows=records['papers']).consume()
    groups = defaultdict(list)
    for row in records['entities']:
        groups[row['label']].append(row)
    for label, rows in groups.items():
        tx.run(f'UNWIND $rows AS row CREATE (n:Entity:{label}) SET n = row, n.id = row.key', rows=rows).consume()
    tx.run('UNWIND $rows AS row MATCH (p:Paper {key:row.paper}), (n:Entity {key:row.entity}) CREATE (p)-[:MENTIONS {experimental:true}]->(n)', rows=records['mentions']).consume()
    groups = defaultdict(list)
    for row in records['relations']:
        groups[row['type']].append({'source': row['source'], 'target': row['target'],
            'key': row['key'], 'paper': row['paper'], 'provenance_json': json.dumps(row, ensure_ascii=False)})
    for kind, rows in groups.items():
        tx.run(f'UNWIND $rows AS row MATCH (a:Entity {{key:row.source}}), (b:Entity {{key:row.target}}) CREATE (a)-[r:{kind}]->(b) SET r = row, r.production_approved = false', rows=rows).consume()


def run(plan, credential_file, output):
    from neo4j import GraphDatabase
    if output.exists():
        raise ValueError('Fresh audit output required')
    manifest, records = load_plan(plan)
    target = manifest['target_database']
    user, password = credentials(credential_file)
    with GraphDatabase.driver('bolt://127.0.0.1:7687', auth=(user, password), max_transaction_retry_time=0) as driver:
        driver.verify_connectivity()
        with driver.session(database='neo4j', default_access_mode='READ') as session:
            before = session.run('MATCH (p:Paper) RETURN count(p) AS n').single()['n']
        with driver.session(database='system') as session:
            names = [r['name'] for r in session.run('SHOW DATABASES YIELD name RETURN name')]
            if target in names:
                raise ValueError('Target already exists; refusing overwrite or resume')
            session.run('CREATE DATABASE `graphrag-review-482` WAIT 30 SECONDS').consume()
        with driver.session(database=target) as session:
            if session.run('MATCH (n) RETURN count(n) AS n').single()['n']:
                raise ValueError('Target must be empty')
            session.run('CREATE CONSTRAINT snapshot_entity_key FOR (n:Entity) REQUIRE n.key IS UNIQUE').consume()
            session.run('CREATE CONSTRAINT snapshot_paper_key FOR (n:Paper) REQUIRE n.key IS UNIQUE').consume()
            session.execute_write(populate, records, manifest['records_sha256'])
            counts = session.run('MATCH (n) RETURN count(n) AS nodes, count(CASE WHEN n:Paper THEN 1 END) AS papers, count(CASE WHEN n:Entity THEN 1 END) AS entities').single().data()
            counts['relationships'] = session.run('MATCH ()-[r]->() RETURN count(r) AS n').single()['n']
        with driver.session(database='neo4j', default_access_mode='READ') as session:
            after = session.run('MATCH (p:Paper) RETURN count(p) AS n').single()['n']
    expected = {'nodes':len(records['papers']) + len(records['entities']) + 1,
                'papers':len(records['papers']), 'entities':len(records['entities']),
                'relationships':len(records['mentions']) + len(records['relations'])}
    result = {'database':target, 'counts':counts, 'expected':expected, 'counts_match':counts == expected,
              'live_papers_before':before, 'live_papers_after':after, 'records_sha256':manifest['records_sha256'],
              'importer_sha256':file_hash(Path(__file__)), 'quality_scores_generated':False}
    atomic_json(output, result)
    if counts != expected:
        raise ValueError('Imported counts differ; audit saved')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--credential-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.plan, args.credential_file, args.output), indent=2))
    except Exception as exc:
        print(json.dumps({'status':'failed', 'exception_type':type(exc).__name__}))
        sys.exit(1)
