import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import urllib.parse

import audit_bibliography_registry as registry


def run(bib,cache,output):
    if output.exists():raise ValueError('Fresh output required')
    declared=registry.entries(bib.read_text(encoding='utf-8'))
    cached={}
    hashes={}
    for entry in declared:
        path=cache/(entry['key']+'.json')
        if path.exists():
            doi=entry.get('doi','').casefold()
            data=json.loads(path.read_text(encoding='utf-8'))
            stored=(data.get('message',{}).get('DOI') or data.get('data',{}).get('attributes',{}).get('doi','')).casefold()
            if doi!=stored:raise ValueError('Cache DOI mismatch: '+entry['key'])
            cached[doi]=data;hashes[path.name]=registry.file_hash(path)
    def cached_fetch(url):
        doi=urllib.parse.unquote(url.split('/works/',1)[-1].split('/dois/',1)[-1]).casefold()
        if doi not in cached:raise FileNotFoundError('No cached registry record')
        return cached[doi]
    output.mkdir(parents=True);responses=output/'registry_responses';responses.mkdir()
    original=registry.fetch
    try:
        registry.fetch=cached_fetch
        records=[registry.check(entry,responses) for entry in declared]
    finally:registry.fetch=original
    registry.atomic_json(output/'audit.json',{'entries':len(records),'status_counts':dict(Counter(r['status'] for r in records)),
        'records':records,'actual_network_requests':0,'actual_llm_api_calls':0,'corrections_applied':False,
        'limits':'Rechecks historical registry snapshots only. Registry disagreement requires primary/version inspection; full-name abbreviation differences may be benign. Missing cache is unresolved, not fabricated.'})
    registry.atomic_json(output/'manifest.json',{'bib_sha256':registry.file_hash(bib),'cache_files_sha256':hashes,
        'code_sha256':{p.name:registry.file_hash(p) for p in [Path(__file__),Path(registry.__file__)]}})
    for p in [Path(__file__),Path(registry.__file__)]:shutil.copy2(p,output/p.name)
    print(json.dumps(dict(Counter(r['status'] for r in records))))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for field in ['bib','cache','output']:parser.add_argument('--'+field,type=Path,required=True)
    run(**vars(parser.parse_args()))
