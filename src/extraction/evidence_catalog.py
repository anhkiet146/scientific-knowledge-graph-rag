"""Offline evidence-ID transport prototype, not the active API runner.

Materializing a citation proves its text/character offsets come from the bound source;
it does not prove that the cited text entails the model's scientific claim.
"""
import hashlib
import json
import copy


def transport_schema(active_schema):
    schema=copy.deepcopy(active_schema)
    for kind in ('entities','relations'):
        item=schema['properties'][kind]['items']
        item['properties'].pop('evidence',None)
        item['properties']['evidence_ids']={'type':'ARRAY','items':{'type':'STRING'}}
        item['required']=[('evidence_ids' if name=='evidence' else name) for name in item['required']]
    return schema


def fingerprint(sections):
    return hashlib.sha256(json.dumps(sections,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def build_catalog(sections, max_characters=600):
    if max_characters < 32:
        raise ValueError('Evidence chunks must allow at least 32 characters')
    if not isinstance(sections,list):raise ValueError('Source sections must be an array')
    seen=set()
    for section in sections:
        if not isinstance(section,dict) or not isinstance(section.get('section_id'),str) or not isinstance(section.get('text'),str):
            raise ValueError('Invalid source section')
        if section['section_id'] in seen:raise ValueError('Duplicate source section ID')
        seen.add(section['section_id'])
    items=[]
    namespace=fingerprint(sections)[:16]
    for section in sections:
        text=section['text']
        if '\ufffd' in text:
            raise ValueError('Corrupt characters must be handled before catalog construction')
        cursor=0
        for line in text.split('\n'):
            left=cursor+len(line)-len(line.lstrip())
            right=cursor+len(line.rstrip())
            while left<right:
                end=min(left+max_characters,right)
                if end<right:
                    boundary=max(text.rfind(' ',left,end+1),text.rfind('\t',left,end+1))
                    if boundary>=left+max_characters//2:end=boundary
                item={'id':f'ev_{namespace}_{len(items):05d}','section_id':section['section_id'],
                      'kind':section.get('kind','body'),'start':left,'end':end,'text':text[left:end]}
                if section.get('page') is not None:item['page']=section['page']
                if section.get('source_quality'):item['source_quality']=section['source_quality']
                items.append(item)
                left=end
                while left<right and text[left].isspace():left+=1
            cursor+=len(line)+1
    return {'prototype':'evidence-id-transport-v1','sections_sha256':fingerprint(sections),'items':items,
            'limits':'Fragments do not resolve table-column mapping or establish semantic entailment.'}


def materialize(payload,catalog,sections):
    if not isinstance(payload,dict) or any(not isinstance(payload.get(k),list) for k in ('entities','relations')):
        raise ValueError('Response must contain entity and relation arrays')
    if not isinstance(catalog,dict) or not isinstance(catalog.get('items'),list):raise ValueError('Invalid evidence catalog')
    if not isinstance(sections,list) or any(not isinstance(s,dict) or not isinstance(s.get('section_id'),str) or not isinstance(s.get('text'),str) for s in sections):
        raise ValueError('Invalid source sections')
    if len({s['section_id'] for s in sections})!=len(sections):raise ValueError('Duplicate source section ID')
    if fingerprint(sections)!=catalog.get('sections_sha256'):
        raise ValueError('Evidence catalog belongs to a different source snapshot')
    sources={s['section_id']:s['text'] for s in sections}
    lookup={}
    for item in catalog['items']:
        if not isinstance(item,dict):raise ValueError('Invalid catalog record')
        start,end=item.get('start'),item.get('end');sid=item.get('section_id')
        if (not isinstance(item.get('id'),str) or item['id'] in lookup or sid not in sources
            or type(start) is not int or type(end) is not int or not 0<=start<end<=len(sources[sid])
            or sources[sid][start:end]!=item.get('text')):
            raise ValueError('Duplicate or modified catalog evidence')
        lookup[item['id']]=item
    output={'entities':[],'relations':[]};issues=[]
    for kind in output:
        for record in payload.get(kind,[]):
            if not isinstance(record,dict):
                issues.append({'kind':kind,'reason':'not_object','item':record});continue
            ids=record.get('evidence_ids')
            if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in lookup for i in ids):
                issues.append({'kind':kind,'reason':'missing_or_unknown_evidence_id','item':record})
                continue
            result={k:v for k,v in record.items() if k not in {'evidence_ids','evidence'}}
            result['evidence']=[]
            for identifier in dict.fromkeys(ids):
                item=lookup[identifier]
                result['evidence'].append({'section_id':item['section_id'],'text':item['text'],
                    'evidence_id':item['id'],'start':item['start'],'end':item['end']})
            output[kind].append(result)
    return output,issues
