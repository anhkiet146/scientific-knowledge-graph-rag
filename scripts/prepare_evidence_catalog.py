"""Prepare the offline evidence-ID prototype; this command makes no API calls."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from reextract_review import sections_from_document,schema,ENTITY_TYPES,SIGNATURES
from evidence_catalog import build_catalog,transport_schema


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():raise ValueError('Use a separate prototype directory')
    args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for source in sorted(args.input.glob('*.json')):
        if source.name.startswith('_'):continue
        document=json.loads(source.read_text(encoding='utf-8'))
        sections=sections_from_document(document)
        catalog=build_catalog(sections)
        if not catalog['items']:raise ValueError('No source evidence: '+source.name)
        request={'prototype':'evidence-id-transport-v1','sections_sha256':catalog['sections_sha256'],
                 'entity_types':ENTITY_TYPES,'relation_signatures':SIGNATURES,
                 'section_metadata':[{k:v for k,v in s.items() if k!='text'} for s in sections],
                 'source_catalog':[{k:item[k] for k in ('id','section_id','text')} for item in catalog['items']]}
        for suffix,value in [('catalog',catalog),('input',request)]:
            (args.output/(source.stem+'.'+suffix+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        records.append({'file':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                        'sections_sha256':catalog['sections_sha256'],'evidence_items':len(catalog['items'])})
    (args.output/'transport_schema.json').write_text(json.dumps(transport_schema(schema()),indent=2),encoding='utf-8')
    (args.output/'manifest.json').write_text(json.dumps({'status':'offline_prototype_not_live_evaluated',
        'api_calls':0,'records':records,'limits':'Exact citation text and character offsets only; semantic correctness and token/cost effects are unmeasured.'},indent=2),encoding='utf-8')
    print(f'Prepared {len(records)} offline prototype catalogs; no API calls')


if __name__=='__main__':main()
