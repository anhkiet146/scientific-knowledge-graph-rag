"""Lossless source occurrences behind conservative typed-name normalization."""
from collections import defaultdict
import json
from normalize_entities import extraction_payload,normalize_surface


def build_ledger(folder):
    groups=defaultdict(list);relations=[];invalid=[]
    for path in sorted(folder.glob('*.json')):
        data=json.loads(path.read_text(encoding='utf-8'));payload=extraction_payload(data);lookup=defaultdict(set)
        for index,entity in enumerate(payload.get('entities',[])):
            name=entity.get('id',entity.get('name',''));kind=entity.get('type','')
            occurrence={'file':path.name,'index':index,'entity':entity}
            if not isinstance(name,str) or not isinstance(kind,str) or not name or not kind:
                invalid.append(occurrence);continue
            key=(kind,normalize_surface(name));groups[key].append(occurrence);lookup[name].add(key)
        for index,relation in enumerate(payload.get('relations',[])):
            source=lookup.get(relation.get('source'),set());target=lookup.get(relation.get('target'),set())
            resolved=len(source)==len(target)==1
            relations.append({'file':path.name,'index':index,'relation':relation,
                              'source_key':list(next(iter(source))) if len(source)==1 else None,
                              'target_key':list(next(iter(target))) if len(target)==1 else None,
                              'state':'resolved' if resolved else 'unresolved_preserved'})
    nodes=[{'key':list(key),'occurrences':value} for key,value in sorted(groups.items())]
    lost_by_first_description=sum(sum(o['entity'].get('description','')!=items[0]['entity'].get('description','') for o in items[1:]) for items in groups.values())
    return nodes,relations,{'valid_entity_occurrences':sum(len(v) for v in groups.values()),'normalized_entities':len(nodes),
                           'relations_preserved':len(relations),'unresolved_relations':sum(r['state']!='resolved' for r in relations),
                           'different_description_occurrences_hidden_by_legacy_first_description':lost_by_first_description,
                           'invalid_entities_preserved':invalid,'policy':'Keep exact original entity/relation objects and file-local indices; no semantic merges or silent drops.'}
