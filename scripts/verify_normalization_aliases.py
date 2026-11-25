"""Check literal PDF acronym declarations; paper-local structural ablation only."""
import argparse
from collections import defaultdict,Counter
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src/extraction')]
from normalization_review_study import surface,literal_surface,SIGNATURES
from workflow_io import atomic_json,canonical_hash,file_hash
from pypdf import PdfReader


def readlines(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').split('\n') if s]


def declaration_pattern(long,short,case_sensitive=False):
    def flexible(text):return re.escape(text).replace(r'\ ',r'\s+').replace(r'\-',r'\s*-\s*')
    return re.compile(r'(?<!\w)'+flexible(long)+r'\s*\(\s*'+flexible(short)+r'\s*\)',0 if case_sensitive else re.I)


def stats(mapping,relations):
    adjacency={v:set() for v in mapping.values()};edges=set()
    for r in relations:
        if r['state']!='resolved':continue
        a,b=[mapping[e['ids'][0]] for e in r['endpoints']]
        edges.add((a,r['source_relation']['type'],b));adjacency[a].add(b);adjacency[b].add(a)
    seen=set();sizes=[]
    for node in sorted(adjacency):
        if node in seen:continue
        todo=[node];seen.add(node);size=0
        while todo:
            current=todo.pop();size+=1
            for neighbor in adjacency[current]-seen:seen.add(neighbor);todo.append(neighbor)
        sizes.append(size)
    return {'nodes':len(adjacency),'directed_typed_edges':len(edges),'isolated_nodes':sum(not v for v in adjacency.values()),'weak_components':len(sizes),'largest_component':max(sizes,default=0)}


def run(study,pdfs,output):
    if output.exists():raise ValueError('Fresh output required')
    source_manifest=json.loads((study/'manifest.json').read_text(encoding='utf-8'))
    policy=source_manifest.get('surface_policy','paper_surface_v1')
    if policy not in {'paper_surface_v1','paper_literal_v2'}:raise ValueError('Unknown study surface policy')
    identity_surface=literal_surface if policy=='paper_literal_v2' else surface
    output.mkdir(parents=True)
    entities=readlines(study/'entities.jsonl');relations=readlines(study/'relations.jsonl');aliases=readlines(study/'alias_review.jsonl')
    papers=defaultdict(list)
    for a in aliases:papers[a['paper']].append(a)
    checks=[];pdf_hashes={}
    for paper,items in sorted(papers.items()):
        pdf=pdfs/(Path(paper).stem+'.pdf');texts=[]
        try:
            digest=file_hash(pdf);pdf_hashes[pdf.name]=digest
            texts=[page.extract_text() or '' for page in PdfReader(pdf).pages]
            error=None
        except Exception as exc:error=type(exc).__name__
        for a in items:
            matches=[];pattern=declaration_pattern(a['long_form'],a['short_form'],case_sensitive=policy=='paper_literal_v2')
            for page,text in enumerate(texts,1):
                for match in pattern.finditer(text):
                    matches.append({'page_pdf':page,'quote':match.group(),'text_start':match.start(),'text_end':match.end()})
            checks.append({**a,'decision':'literal_pdf_declaration_found' if matches else 'pending_source_review',
                'pdf_text_verified':bool(matches),'pdf_sha256':pdf_hashes.get(pdf.name),'pdf_file':pdf.name,'matches':matches,
                'error':error,'semantic_role_verified':False,'independent_annotation':False})
        if not error and file_hash(pdf)!=pdf_hashes[pdf.name]:raise ValueError('PDF changed during audit')
    # Ambiguous same-paper acronym declarations remain blocked.
    definitions=defaultdict(set)
    for a in checks:
        if a['matches']:definitions[(a['paper'],a['type'],identity_surface(a['short_form']))].add(identity_surface(a['long_form']))
    accepted=[]
    for a in checks:
        if a['matches'] and len(definitions[a['paper'],a['type'],identity_surface(a['short_form'])])==1:accepted.append(a)
        elif a['matches']:a['decision']='ambiguous_acronym_do_not_merge'
    byid={e['occurrence_id']:e for e in entities};parent={k:k for k in byid}
    def find(k):
        while parent[k]!=k:parent[k]=parent[parent[k]];k=parent[k]
        return k
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    index=defaultdict(list)
    for e in entities:index[e['paper'],e['type'],identity_surface(e['name'])].append(e['occurrence_id'])
    base=json.loads((study/'identity_maps.json').read_text(encoding='utf-8'))
    surface_groups=defaultdict(list)
    for oid,key in base['surface'].items():surface_groups[key].append(oid)
    for group in surface_groups.values():
        for oid in group[1:]:union(group[0],oid)
    lookup=defaultdict(set)
    for a in accepted:
        members={a['occurrence_id']}
        for name in (a['long_form'],a['short_form']):members.update(index[a['paper'],a['type'],identity_surface(name)])
        for oid in members:union(a['occurrence_id'],oid)
        for name in (a['long_form'],a['short_form']):lookup[a['paper'],a['type'],identity_surface(name)].update(members)
    repaired=[];rescued=0
    for original in relations:
        row=json.loads(json.dumps(original));signature=SIGNATURES.get(row['source_relation'].get('type'))
        if signature:
            for field,kind,end in zip(('source','target'),signature,row['endpoints']):
                if end['state']=='exact':continue
                candidates=lookup[row['paper'],kind,identity_surface(str(row['source_relation'].get(field,'')))]
                representatives={find(oid) for oid in candidates}
                if len(representatives)==1:
                    end.update(state='pdf_declared_alias',ids=[sorted(candidates)[0]])
            row['state']='resolved' if all(e['state'] in {'exact','pdf_declared_alias'} for e in row['endpoints']) else 'quarantined'
        rescued+=row['state']=='resolved' and original['state']!='resolved'
        repaired.append(row)
    mapping={oid:find(oid) for oid in byid}
    for name,rows in [('alias_pdf_checks',checks),('relations_alias_track',repaired)]:
        with (output/(name+'.jsonl')).open('w',encoding='utf-8') as f:
            for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'identity_maps.json',{'raw':base['raw'],'surface':base['surface'],'pdf_declared_alias':mapping})
    summary={'alias_candidates':len(checks),'literal_pdf_declarations':sum(bool(a['matches']) for a in checks),
        'unambiguous_pdf_declared_aliases':len(accepted),'remaining_source_review':sum(not a['matches'] for a in checks),
        'ambiguous_declarations':sum(a['decision']=='ambiguous_acronym_do_not_merge' for a in checks),
        'rescued_typed_relations':rescued,'relation_states':dict(Counter(r['state'] for r in repaired)),
        'structural_comparison':{'raw':stats(base['raw'],relations),'surface':stats(base['surface'],relations),'pdf_declared_alias':stats(mapping,repaired)},
        'actual_api_calls':0,'quality_scores_computed':False,'approved_for_production_graph':False,
        'surface_policy':policy,'pdf_matching_case_sensitive':policy=='paper_literal_v2',
        'limits':'Literal parenthetical matches in PDF extracted text; not visual expert review or independent gold. Reference/background declarations may match; scientific role and relation entailment remain unverified. No cross-paper merges, semantic-synonym recall or QA improvement claimed.'}
    atomic_json(output/'summary.json',summary)
    atomic_json(output/'manifest.json',{'code_sha256':file_hash(Path(__file__)),'normalization_code_sha256':file_hash(ROOT/'scripts/normalization_review_study.py'),
        'surface_policy':policy,'inputs':{p.name:file_hash(p) for p in [study/'entities.jsonl',study/'relations.jsonl',study/'alias_review.jsonl',study/'identity_maps.json']},'pdf_sha256':pdf_hashes})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('study','pdfs','output'):p.add_argument('--'+flag,type=Path,required=True)
    run(**vars(p.parse_args()))
