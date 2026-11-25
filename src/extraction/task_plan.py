"""Deterministic source partition; table hints do not establish column correctness."""
import re
try:
    from .reextract_review import sections_from_document
    from .evidence_catalog import build_catalog
except ImportError:
    from reextract_review import sections_from_document
    from evidence_catalog import build_catalog

def plan(document,max_items=100):
    if not 20<=max_items<=200:raise ValueError('Use an evidence-item limit between 20 and 200')
    sections=sections_from_document(document);catalog=build_catalog(sections)
    items=catalog['items'];lookup={i['id']:i for i in items}
    metadata=[i['id'] for i in items if i['kind'] in {'title','header','abstract'}]
    body=[i['id'] for i in items if i['kind'] not in {'title','header','abstract'}]
    captions={}
    for index,item in enumerate(items):
        if re.match(r'^Table\s*\d+[.:]',item['text'],re.I):
            # Candidate context, not verified table structure or column mapping.
            nearby=[x['id'] for x in items[index:index+4] if x.get('page')==item.get('page')]
            captions.setdefault(item.get('page'),[]).extend(nearby)
    tasks=[]
    if metadata:tasks.append({'task_id':'metadata','scope_ids':metadata,'context_ids':[],
                              'purpose':'article metadata and core supported entities'})
    for index in range(0,len(body),max_items):
        scope=body[index:index+max_items];pages=sorted({lookup[i].get('page') for i in scope},key=lambda p:(p is None,str(p)))
        context=list(dict.fromkeys(metadata+[i for p in pages for i in captions.get(p,[])]))
        context=[i for i in context if i not in scope]
        tasks.append({'task_id':f'body_{index//max_items+1:03d}','scope_ids':scope,'context_ids':context,
                      'purpose':'supported findings in scope; context does not authorize unrelated findings',
                      'candidate_table_context_requires_review':True})
    all_ids=[i for t in tasks for i in t['scope_ids']]
    if len(all_ids)!=len(set(all_ids)) or set(all_ids)!=set(lookup):raise ValueError('Task coverage is not an exact partition')
    for task in tasks:
        chosen=task['context_ids']+task['scope_ids']
        task['input_characters']=sum(len(lookup[i]['text']) for i in chosen)
        task['evidence']=[{k:lookup[i][k] for k in ('id','section_id','text')} for i in chosen]
    return {'status':'planned_not_executed','source_sections_sha256':catalog['sections_sha256'],
            'catalog':catalog,'tasks':tasks,'planned_initial_api_calls':len(tasks),'actual_api_calls':0,
            'limits':'Planning makes no API calls. Caption/header candidates are unverified; execution receipts and semantic review are required separately. Not approved for batch extraction.'}
