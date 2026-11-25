"""Prepare blind pending tasks from a fixed sample; never migrate old labels."""
import argparse
import csv
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction'),str(ROOT/'scripts')]
from workflow_io import read_json,atomic_json,file_hash
from reextract_review import sections_from_document
from prepare_review_dataset import read_questions


def prepare(sample,corpus,pdfs,development,questions,output,*,expected_papers=40,expected_questions=45):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Fresh annotation bundle required')
    for source in (corpus,pdfs,development):
        if Path(source).resolve().is_relative_to(output) or output.is_relative_to(Path(source).resolve()):
            raise ValueError('Separate annotation output required')
    with Path(sample).open(encoding='utf-8-sig',newline='') as stream:selection=list(csv.DictReader(stream))
    if len(selection)!=expected_papers:raise ValueError('Wrong fixed sample size')
    stems=[Path(r['filename']).stem for r in selection];paper_ids=[r['paper_id'] for r in selection]
    if len(set(stems))!=len(stems) or len(set(paper_ids))!=len(paper_ids):raise ValueError('Duplicate sample papers')
    for row in selection:
        if Path(row['filename']).name!=row['filename'] or Path(row['filename']).suffix.lower()!='.pdf':raise ValueError('Unsafe sample filename')
    dev={p.stem for p in Path(development).glob('*.json') if not p.name.startswith('_')}
    if set(stems)&dev:raise ValueError('Evaluation sample overlaps known development inputs')
    tasks=[];sources=[]
    for row,stem in zip(selection,stems):
        source=Path(corpus)/(stem+'.json');pdf=Path(pdfs)/row['filename'];doc=read_json(source)
        if not pdf.is_file():raise ValueError('Missing original PDF')
        tasks.append({'protocol_id':'strict-extraction-v3.1','paper_id':row['paper_id'],'filename':row['filename'],
            'source_sha256':file_hash(source),'source_pdf_sha256':file_hash(pdf),'pdf_path':'pdfs/'+pdf.name,
            'sections':sections_from_document(doc),'entities':[],'relations':[],'annotation_status':'pending',
            'completed_by':None,'completed_at':None,'independence_attestation':None,'notes':'',
            'annotators':[],'adjudication_log':[]})
        sources.append((source,pdf))
    qa=read_questions(questions)
    if len(qa)!=expected_questions or len({q['question'] for q in qa})!=len(qa):raise ValueError('Wrong QA set or duplicate questions')
    qa_tasks=[{'question_id':i,'question':q['question'],'reference_answer':None,'answerability':None,
        'source_evidence':[],'annotation_status':'pending','completed_by':None,'notes':''} for i,q in enumerate(qa,1)]
    output.mkdir(parents=True)
    for folder in ('pdfs','prepared_sources'):(output/folder).mkdir()
    for source,pdf in sources:
        shutil.copyfile(source,output/'prepared_sources'/source.name);shutil.copyfile(pdf,output/'pdfs'/pdf.name)
    for label in ('A','B'):
        with (output/f'annotator_{label}_extraction.jsonl').open('w',encoding='utf-8') as stream:
            import json
            for task in tasks:stream.write(json.dumps(task,ensure_ascii=False)+'\n')
        atomic_json(output/f'annotator_{label}_qa.json',{'protocol_id':'independent-qa-v1.1','annotator_role':label,
            'instructions':'Work independently from original PDFs. Do not inspect model outputs, old answers or the other annotator. Blank tasks are not labels.',
            'tasks':qa_tasks})
    for name in ('strict_protocol_v3_1.json',):shutil.copyfile(ROOT/'configs'/name,output/name)
    shutil.copyfile(ROOT/'schemas/extracted_kg_strict_v3_1.schema.json',output/'extracted_kg_strict_v3_1.schema.json')
    shutil.copyfile(ROOT/'docs/ANNOTATION_V3_1_VI.md',output/'ANNOTATION_V3_1_VI.md')
    manifest={'protocol_id':'blind-annotation-bundle-v3.1','sample_manifest_sha256':file_hash(sample),
        'n_papers':len(tasks),'n_questions':len(qa_tasks),'known_development_input_count':len(dev),
        'development_overlap':[],'labels_completed':0,'independent_gold_ready':False,
        'source_hash_policy':'source_sha256 is prepared JSON for scoring; source_pdf_sha256 separately binds the full original PDF. Historic CSV hash is not silently reused for a different parser output.',
        'files':[{'path':p.relative_to(output).as_posix(),'sha256':file_hash(p)} for p in sorted(output.rglob('*')) if p.is_file()]}
    # Validate copied inputs against hashes captured before copying.
    for task,(source,pdf) in zip(tasks,sources):
        if file_hash(output/'prepared_sources'/source.name)!=task['source_sha256'] or file_hash(output/'pdfs'/pdf.name)!=task['source_pdf_sha256']:
            raise ValueError('Source changed during annotation preparation')
    atomic_json(output/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('sample','corpus','pdfs','development','questions','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();result=prepare(**vars(args));print('Prepared pending A/B tasks:',result['n_papers'],'papers,',result['n_questions'],'QA; labels: 0')
