"""Prepare unlabelled human review records from immutable task receipts."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,read_json,loads,canonical_hash,file_hash
from chunk_runner import verify_task


def prepare(source):
    records=[];unparseable_tasks=[]
    for receipt in sorted((source/'tasks').glob('*/*/receipt.json')):
        folder=receipt.parent;result=verify_task(folder)
        spec=read_json(folder/'spec.json');response=read_json(folder/'response.json')
        request=read_json(folder/'request.json')
        # Recover the exact catalog actually sent, not a newly generated catalog.
        marker='\nCURRENT TASK:\n'
        if marker not in request['prompt']:raise ValueError('Missing task source envelope')
        envelope=loads(request['prompt'].split(marker,1)[1])
        catalog={e['id']:e for e in envelope['evidence_catalog']}
        metadata={s['section_id']:s for s in envelope['section_metadata']}
        try:
            payload=loads(response['text'])
            if (not isinstance(payload,dict) or any(not isinstance(payload.get(k),list)
                or any(not isinstance(i,dict) for i in payload[k]) for k in ('entities','relations'))):
                raise ValueError('Invalid record arrays')
        except (ValueError,TypeError) as exc:
            unparseable_tasks.append({'paper_key':folder.parent.name,'task_id':folder.name,
                'reason':str(exc),'response_sha256':file_hash(folder/'response.json')})
            continue
        for kind in ('entities','relations'):
            for index,item in enumerate(payload[kind]):
                flags=[i for i in result['validation_issues'] if i.get('item',{}).get('id')==item.get('id')]
                if kind=='relations':
                    flags=[i for i in result['validation_issues'] if all(
                        i.get('item',{}).get(k)==item.get(k) for k in ('source','target','type'))]
                cited=[]
                references=item.get('evidence_ids',[])
                if not isinstance(references,list):references=[references]
                for eid in references:
                    if not isinstance(eid,str) or eid not in catalog:
                        cited.append({'unresolved_evidence_id':eid});continue
                    entry=catalog[eid];section=metadata[entry['section_id']]
                    cited.append({**entry,'section_kind':section.get('kind'),
                        'in_scope':eid in spec['scope_ids']})
                key=[folder.parent.name,folder.name,kind,index,canonical_hash(item)]
                records.append({'record_id':canonical_hash(key),'paper_key':folder.parent.name,
                    'task_id':folder.name,'record_kind':kind,'raw_record':item,'cited_source':cited,
                    'automated_flags':[{'reason':i['reason'],'details':i.get('details',[])} for i in flags],
                    'review':{'status':'unreviewed','reviewer':'','decision':'','notes':'',
                        'source_attribution_correct':None,'entity_type_or_relation_correct':None,
                        'measurement_fields_correct':None}})
    return {'purpose':'Development candidate review, not independent gold or completed evaluation',
        'source_manifest_sha256':file_hash(source/'manifest.json'),
        'instructions':'Inspect every record against its cited source and original PDF. Automated flags are not expert labels. Do not approve a whole paper from a partial task.',
        'records':records,'unparseable_tasks':unparseable_tasks,'reviewed_record_count':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();atomic_json(args.output,prepare(args.run.resolve()))
