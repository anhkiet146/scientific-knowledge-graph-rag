"""Source-preserving normalization comparison, no API or independent quality claims."""
import argparse
from collections import defaultdict,Counter
import json
from pathlib import Path
import re
import sys
import unicodedata
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'src/normalization')]
from workflow_io import atomic_json,file_hash,canonical_hash
from normalize_entities import extraction_payload

SIGNATURES={'BELONGS_TO':('Concept','Domain'),'USED_FOR':('Method','Concept'),'EVALUATED_ON':('Method','Dataset'),'ACHIEVED':('Method','Metric'),'AFFILIATED_WITH':('Author','Institution')}


def surface(name):
    # Preserve punctuation, signs, dose and model variants; do not reuse the
    # historical punctuation-stripping normalizer as a scientific identity rule.
    return ' '.join(unicodedata.normalize('NFKC',name).casefold().split())

def literal_surface(name):
    if not isinstance(name,str) or not name.strip():
        raise ValueError('Nonempty source name required')
    return ' '.join(unicodedata.normalize('NFC',name).split())

def study(folder,output,surface_policy='paper_surface_v1'):
    if surface_policy not in {'paper_surface_v1','paper_literal_v2'}:
        raise ValueError('Unknown surface policy')
    identity_surface=literal_surface if surface_policy=='paper_literal_v2' else surface
    if output.exists():raise ValueError('Fresh output required')
    output.mkdir(parents=True);occurrences=[];relations=[];aliases=[];before={}
    for path in sorted(folder.glob('*.json')):
        if path.name.startswith('_'):continue
        before[path.name]=file_hash(path);d=json.loads(path.read_text(encoding='utf-8'));p=extraction_payload(d);local=defaultdict(list)
        for index,entity in enumerate(p.get('entities',[])):
            name=entity.get('name') or entity.get('id','');kind=entity.get('type','');oid=f'{path.name}:e{index}'
            if not isinstance(name,str) or not name or not kind:raise ValueError('Invalid entity requires explicit repair')
            occurrence={'occurrence_id':oid,'paper':path.name,'type':kind,'source_entity':entity,'name':name}
            occurrences.append(occurrence);local[entity.get('id',name)].append(occurrence)
            match=re.fullmatch(r'(.+?)\s*\(([A-Za-z][A-Za-z0-9-]{1,15})\)',name)
            if match and kind not in {'Author','Institution','Metric'}:
                # Declaration in extraction name only: not evidence of PDF
                # validation and never permission to merge different papers.
                aliases.append({'paper':path.name,'type':kind,'long_form':match[1].strip(),'short_form':match[2],
                                'occurrence_id':oid,'source':'parenthetical_name_in_historical_extraction',
                                'pdf_verified':False,'decision':'pending_source_review'})
        for index,relation in enumerate(p.get('relations',[])):
            signature=SIGNATURES.get(relation.get('type'));ends=[]
            for field,kind in zip(('source','target'),signature or (None,None)):
                candidates=[e for e in local.get(relation.get(field),[]) if e['type']==kind]
                if not candidates and kind:
                    declared=[a for a in aliases if a['paper']==path.name and a['type']==kind and surface(a['short_form'])==surface(str(relation.get(field,'')))]
                    candidates=[e for values in local.values() for e in values if any(e['occurrence_id']==a['occurrence_id'] for a in declared)]
                    # Keep as proposed resolution, not an accepted graph edge.
                    ends.append({'state':'proposed_alias' if len(candidates)==1 else 'unresolved','ids':[e['occurrence_id'] for e in candidates]});continue
                ends.append({'state':'exact' if len(candidates)==1 else 'unresolved','ids':[e['occurrence_id'] for e in candidates]})
            relations.append({'paper':path.name,'index':index,'source_relation':relation,'endpoints':ends,
                              'state':'resolved' if signature and all(e['state']=='exact' for e in ends) else 'quarantined'})
    byid={o['occurrence_id']:o for o in occurrences}
    # Surface scope is paper-local to avoid silently merging cross-paper homonyms.
    def identity(o,policy):
        if policy=='raw':return o['occurrence_id']
        if o['type']=='Metric':return o['occurrence_id']
        return canonical_hash([o['paper'],o['type'],identity_surface(o['name'])])
    summaries={};maps={}
    for policy in ('raw','surface'):
        mapping={oid:identity(o,policy) for oid,o in byid.items()};maps[policy]=mapping
        nodes=set(mapping.values());adj={n:set() for n in nodes};edges=set()
        for r in relations:
            if r['state']!='resolved':continue
            a,b=[mapping[e['ids'][0]] for e in r['endpoints']]
            edges.add((a,r['source_relation']['type'],b));adj[a].add(b);adj[b].add(a)
        seen=set();sizes=[]
        for node in sorted(nodes):
            if node in seen:continue
            todo=[node];seen.add(node);count=0
            while todo:
                current=todo.pop();count+=1
                for neighbor in adj[current]-seen:seen.add(neighbor);todo.append(neighbor)
            sizes.append(count)
        summaries[policy]={'nodes':len(nodes),'directed_typed_edges':len(edges),'isolated_nodes':sum(not v for v in adj.values()),
                           'weak_components':len(sizes),'largest_component':max(sizes,default=0)}
    groups=defaultdict(list)
    for o in occurrences:groups[(o['type'],surface(o['name']))].append(o)
    cross=[{'type':kind,'surface':name,'papers':sorted({o['paper'] for o in values}),'decision':'not_merged_cross_paper_identity_unverified'}
           for (kind,name),values in groups.items() if len({o['paper'] for o in values})>1]
    for name,rows in [('entities',occurrences),('relations',relations),('alias_review',aliases),('cross_paper_review',cross)]:
        with (output/(name+'.jsonl')).open('w',encoding='utf-8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'identity_maps.json',maps)
    for name,digest in before.items():
        if file_hash(folder/name)!=digest:raise ValueError('Input changed')
    atomic_json(output/'summary.json',{'papers':len(before),'entity_occurrences':len(occurrences),'relation_occurrences':len(relations),
        'structural_comparison':summaries,'relation_states':dict(Counter(r['state'] for r in relations)),
        'proposed_alias_endpoints':sum(e['state']=='proposed_alias' for r in relations for e in r['endpoints']),
        'alias_declarations_pending_pdf_review':len(aliases),'cross_paper_name_groups_pending_disambiguation':len(cross),
        'source_files_unchanged':True,'actual_api_calls':0,'qa_scores_computed':False,'surface_policy':surface_policy,
        'alias_track':'Prepared candidate queue only; no approved source-reviewed alias map yet, so no fabricated alias-treatment result',
        'limits':'Paper-local structural diagnostics, not synonym recall, extraction accuracy or QA improvement. Quarantined relations preserved. Compare same questions and evidence budget after approved aliases; paired QA effect pending.'})
    atomic_json(output/'manifest.json',{'source_files_sha256':before,'code_sha256':file_hash(Path(__file__)),
        'surface_policy':surface_policy,
        'policy':('Paper-local NFC and whitespace only; preserve case, compatibility characters, punctuation, scientific signs and each Metric occurrence.'
                  if surface_policy=='paper_literal_v2' else
                  'Paper-local NFKC/casefold/whitespace only; preserve punctuation, all source objects and Metric occurrences. Never auto-merge semantic similarity or cross-paper homonyms.'),
        'output_status':'development_normalization_study_not_gold_not_production_graph'})
    print((output/'summary.json').read_text(encoding='utf-8'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--surface-policy',choices=['paper_surface_v1','paper_literal_v2'],default='paper_surface_v1')
    a=p.parse_args();study(a.input,a.output,a.surface_policy)
