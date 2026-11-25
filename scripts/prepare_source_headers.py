"""Attach reviewed, source-bound header spans to extraction-only copies."""
import argparse
import copy
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,atomic_json,file_hash
from task_plan import plan


def attach_header(document,decision):
    if document.get('raw_header'):raise ValueError('Existing header must not be overwritten')
    if decision.get('review_status')!='assistant_visual_source_check_not_independent':raise ValueError('Explicit source review required')
    if not document.get('sections') or document['sections'][0].get('page')!=1:raise ValueError('First PDF page required')
    text=document['sections'][0]['content'];start,end=decision['start'],decision['end']
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text):raise ValueError('Invalid header source span')
    header=text[start:end]
    if len(header)>5000 or '\ufffd' in header or re.search(r'Academic Editor|Citation:',header,re.I):
        raise ValueError('Header needs further source review')
    result=copy.deepcopy(document)
    if not result.get('title'):
        a,b=decision['title_span']
        if type(a) is not int or type(b) is not int or not start<=a<b<=end:raise ValueError('Title must occur in selected header')
        result['title']=' '.join(text[a:b].split())
    if ' '.join(result['title'].casefold().split()) not in ' '.join(header.casefold().split()):
        raise ValueError('Article title is not in selected header')
    result['raw_header']=header
    result['header_provenance']={'source_corpus_document_sha256':decision['source_sha256'],
        'page':1,'source_section_index':0,'start':start,'end':end,
        'review_status':decision['review_status'],
        'scope':'Derived extraction input only; same literal text remains in the frozen source page. Not independent author/affiliation annotation.'}
    return result


def prepare(dataset,decisions,output):
    if output.exists():raise ValueError('Fresh output required')
    manifest=read_json(dataset/'manifest.json');review=read_json(decisions)
    additions={r['corpus_file'] for r in manifest['additions']}
    if set(review)!=additions:raise ValueError('Header decisions must cover exactly six supplements')
    declared={r['path']:r['sha256'] for r in manifest['files']}
    prepared=[]
    for name in sorted(additions):
        source=dataset/'corpus'/name;decision=review[name]
        if file_hash(source)!=declared['corpus/'+name] or file_hash(source)!=decision['source_sha256']:
            raise ValueError('Source changed after header review')
        document=attach_header(read_json(source),decision);tasks=plan(document,100)
        if not any(i['kind']=='header' for i in tasks['catalog']['items']):raise ValueError('No eligible header evidence created')
        prepared.append((name,document,tasks))
    output.mkdir(parents=True);rows=[]
    for name,document,tasks in prepared:
        atomic_json(output/'documents'/name,document);atomic_json(output/'plans'/name,tasks)
        rows.append({'file':name,'header_characters':len(document['raw_header']),
            'eligible_header_evidence_ids':[i['id'] for i in tasks['catalog']['items'] if i['kind']=='header'],
            'planned_root_tasks':len(tasks['tasks']),'document_sha256':file_hash(output/'documents'/name),
            'plan_sha256':file_hash(output/'plans'/name)})
    summary={'state':'extraction_inputs_prepared_not_extracted','documents':rows,
        'initial_tasks':sum(r['planned_root_tasks'] for r in rows),'api_calls':0,
        'source_corpus_changed':False,'parent_manifest_sha256':file_hash(dataset/'manifest.json'),
        'decisions_sha256':file_hash(decisions),'code_sha256':file_hash(Path(__file__)),
        'limits':'Header spans reviewed by assistant, not independent gold. All affiliation and extraction correctness remains ungraded. Old pilot responses bind different input/catalog hashes and cannot be presented as outputs of these inputs.'}
    atomic_json(output/'manifest.json',summary);print('Prepared',len(rows),'source-bound headers;',summary['initial_tasks'],'initial tasks; API calls:0')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','decisions','output'):p.add_argument('--'+name,type=Path,required=True)
    prepare(**vars(p.parse_args()))
