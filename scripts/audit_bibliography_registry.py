"""Conservative primary-registry bibliography audit; never rewrites references."""
import argparse
import concurrent.futures
import collections
import difflib
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.request
import urllib.parse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash


def braced(text,start):
    depth=0
    for index in range(start,len(text)):
        if text[index]=='{' and (index==0 or text[index-1]!='\\'):depth+=1
        if text[index]=='}' and (index==0 or text[index-1]!='\\'):
            depth-=1
            if depth==0:return text[start+1:index],index+1
    raise ValueError('Unbalanced bibliography braces')


def entries(text):
    result=[]
    for match in re.finditer(r'@(\w+)\s*\{([^,\s]+),',text):
        body,_=braced(text,text.index('{',match.start()));fields={}
        position=body.index(',')+1
        while position<len(body):
            field=re.match(r'\s*,?\s*(\w+)\s*=\s*\{',body[position:])
            if not field:
                if body[position:].strip(' ,\r\n\t'):raise ValueError('Unsupported bibliography field syntax')
                break
            start=position+field.end()-1
            value,position=braced(body,start);fields[field[1].lower()]=value
        result.append({'key':match[2],'entry_type':match[1].lower(),**fields})
    if not result or len({r['key'] for r in result})!=len(result):raise ValueError('Missing entries or duplicate bibliography keys')
    return result


def norm(text):
    text=re.sub(r'\\[\"\'`^~]\s*\{?([A-Za-z])\}?',r'\1',text)
    text=''.join(c for c in unicodedata.normalize('NFKD',text) if unicodedata.category(c)!='Mn')
    return ' '.join(re.findall(r'\w+',text.replace('{','').replace('}','').casefold()))


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'ScientificExtraction-bibliography-audit/1.0'})
    with urllib.request.urlopen(request,timeout=25) as response:
        raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('Registry response too large')
        return json.loads(raw.decode())


def author_issues(declared, families, full_names):
    names=[norm(s) for s in declared.split(' and ') if s.strip()]
    issues=[]
    if families and len(names)!=len(families):issues.append('author_count_differs')
    if any(a and not any(set(norm(a).split())<=set(n.split()) for n in names) for a in families):
        issues.append('author_metadata_incomplete_or_differs')
    if 'others' in names:issues.append('truncated_author_list_requires_review')
    if full_names and all(full_names) and len(names)==len(full_names):
        tokens=lambda s:sorted(norm(s).split())
        if any(tokens(a)!=tokens(b) for a,b in zip(names,full_names)):
            issues.append('author_full_name_or_order_differs')
    return issues


def check(entry,folder):
    doi=entry.get('doi','').strip();record={'key':entry['key'],'declared':entry,'doi':doi,'corrections_applied':False}
    if not doi:return {**record,'status':'no_doi_manual_verification_required'}
    provider='datacite' if doi.lower().startswith('10.48550/') else 'crossref'
    url=('https://api.datacite.org/dois/' if provider=='datacite' else 'https://api.crossref.org/works/')+urllib.parse.quote(doi,safe='/')
    record.update(registry=provider,registry_url=url)
    try:
        data=fetch(url);atomic_json(folder/(entry['key']+'.json'),data)
        if provider=='crossref':
            d=data['message'];titles=d.get('title',[]);authors=[a.get('family','') for a in d.get('author',[])]
            full_names=[' '.join((a['given'],a['family'])) if a.get('given') and a.get('family') else '' for a in d.get('author',[])]
            years=[v['date-parts'][0][0] for k,v in d.items() if k in {'issued','published','published-print','published-online'} and isinstance(v,dict) and v.get('date-parts')]
            pages=d.get('page');kind=d.get('type');volume=d.get('volume');venue=d.get('container-title',[])
        else:
            d=data['data']['attributes'];titles=[t['title'] for t in d.get('titles',[])];authors=[a.get('familyName') or a.get('name','') for a in d.get('creators',[])]
            full_names=[a.get('name','') for a in d.get('creators',[])]
            years=[d.get('publicationYear')];pages=None;kind=d.get('types',{}).get('resourceTypeGeneral');volume=None;venue=[d.get('publisher','')]
        title_match=any(norm(entry.get('title',''))==norm(t) for t in titles)
        year_match=entry.get('year') in {str(y) for y in years}
        issues=author_issues(entry.get('author',''),authors,full_names)
        if not title_match:issues.append('title_differs')
        if not year_match:issues.append('year_differs')
        if pages and entry.get('pages') and re.sub(r'\D','',pages)!=re.sub(r'\D','',entry['pages']):issues.append('page_range_differs')
        if volume and entry.get('volume') and norm(volume)!=norm(entry['volume']):issues.append('volume_differs')
        if provider=='datacite' and entry['entry_type']=='inproceedings':issues.append('preprint_doi_used_for_conference_entry_check_version')
        record.update(status='core_metadata_agrees' if not issues else 'manual_metadata_review_required',issues=issues,
            registered_titles=titles,registered_author_family_or_creator_names=authors,registered_years=years,
            registered_author_full_names=full_names,
            registered_pages=pages,registered_volume=volume,registered_venue=venue,registered_type=kind,
            title_similarity_diagnostic=max((difflib.SequenceMatcher(None,norm(entry.get('title','')),norm(t)).ratio() for t in titles),default=0),
            limits='Core registry metadata only; author full-name/order, version, venue and every bibliographic field are not automatically certified.')
    except Exception as exc:record.update(status='registry_lookup_unresolved',error_type=type(exc).__name__,limits='Lookup failure is not evidence of a fictitious reference.')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bib',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh registry audit directory required')
    data=entries(args.bib.read_text(encoding='utf-8'));args.output.mkdir(parents=True);raw=args.output/'registry_responses';raw.mkdir()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda row:check(row,raw),data))
    dois=collections.Counter(e.get('doi','').casefold() for e in data if e.get('doi'))
    atomic_json(args.output/'audit.json',{'source_bib_sha256':file_hash(args.bib),'entries':len(data),
        'status_counts':dict(collections.Counter(r['status'] for r in results)),'duplicate_dois':[d for d,n in dois.items() if n>1],
        'records':results,'corrections_applied':False,'limitations':'No reference silently rewritten. Registry agreement is not full editorial certification; unresolved/mismatched records need primary-source inspection.'})
    print('Registry audit:',dict(collections.Counter(r['status'] for r in results)),flush=True)
