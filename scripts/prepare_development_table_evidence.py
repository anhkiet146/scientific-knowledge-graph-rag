"""Explicit layouts for two development tables, not a general table detector."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import atomic_json,file_hash
from table_evidence import extract_table


def rice_spec(path):
    cells=[];observations=[]
    def cell(key,role,box):cells.append({'id':key,'role':role,'bbox':box})
    cell('caption','caption',[51,394,489,408])
    cell('epochs_header','condition_label',[172,408.5,211,421.5])
    for name,left,right in [('resnet',240,300),('large',300,398),('small',398,489)]:
        cell(name,'object',[left,408.5,right,421.5])
    tops=[422.82,434.22,445.74,457.74,469.26,480.78,492.78,504.33,515.85,
          527.85,539.25,550.77,562.77,574.29,585.81]
    for group,(top,bottom) in enumerate([(421.8,456.8),(456.8,491.8),(491.8,526.8),(526.8,561.8),(561.8,596.8)]):
        cell('endpoint_'+str(group),'endpoint',[51,top,172,bottom])
    for index,top in enumerate(tops):
        cell('epoch_'+str(index),'condition',[190,top-.2,210,top+10.2])
        for name,left,right in [('resnet',240,300),('large',300,398),('small',398,489)]:
            key=f'value_{index}_{name}';cell(key,'value',[left,top-.2,right,top+10.2])
            observations.append({'id':f'row_{index}_{name}','cells':{'caption':'caption','object':name,
                'endpoint':'endpoint_'+str(index//3),'condition':'epoch_'+str(index),'condition_label':'epochs_header','value':key}})
    return {'table_id':'rice_table_2','page':5,'source_sha256':file_hash(path),'cells':cells,'observations':observations,
        'layout_origin':'Explicit coordinates on a development page; no independent gold labels'}


def oil_spec(path):
    cells=[{'id':'caption','role':'caption','bbox':[51,100,260,136]},
        {'id':'unit','role':'unit','bbox':[150,140,258,151.7]},
        {'id':'reporting_note','role':'reporting_note','bbox':[51,237.5,220,248]},
        {'id':'dpph','role':'endpoint','bbox':[110,152,184,163.4]},
        {'id':'abts','role':'endpoint','bbox':[184,152,258,163.4]}]
    observations=[]
    for index,top in enumerate([164,175.5,187,198.5,210,221.5]):
        key=f'object_{index}';cells.append({'id':key,'role':'object','bbox':[51,top,110,top+11.4]})
        for name,left,right in [('dpph',110,184),('abts',184,258)]:
            value=f'value_{index}_{name}'
            cells.append({'id':value,'role':'value','bbox':[left,top,right,top+11.4]})
            observations.append({'id':f'row_{index}_{name}','cells':{'caption':'caption','object':key,
                'endpoint':name,'unit':'unit','value':value,'reporting_note':'reporting_note'}})
    return {'table_id':'oil_table_6','page':8,'source_sha256':file_hash(path),'cells':cells,'observations':observations,
        'layout_origin':'Explicit coordinates on a development page; corrupt source characters not repaired'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf-directory',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for filename,builder in [('01-1108-NGO DUC LUU(1-7)316.pdf',rice_spec),('01-590-Shola H. Awojide(1-11)046.pdf',oil_spec)]:
        path=args.pdf_directory/filename;spec=builder(path);result=extract_table(path,spec)
        atomic_json(args.output/(spec['table_id']+'_spec.json'),spec)
        atomic_json(args.output/(spec['table_id']+'_evidence.json'),result)
        reports.append({'table_id':spec['table_id'],'observations':len(result['observations']),
            'blocked_source_text':sum(bool(o['issues']) for o in result['observations']),
            'pending_review':sum(not o['issues'] for o in result['observations'])})
    atomic_json(args.output/'summary.json',{'tables':reports,'actual_api_calls':0,'graph_writes':0,'independent_gold':False})


if __name__=='__main__':main()
