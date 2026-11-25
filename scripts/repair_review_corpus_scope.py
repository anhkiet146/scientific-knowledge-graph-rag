"""Build a separate source-only corpus, preserving the historical482 snapshot."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src/extraction'), str(ROOT/'scripts')]
from workflow_io import atomic_json, file_hash
from prepare_review_dataset import verify


def require_source_phrase(pages, phrase):
    hits = []
    for page in pages:
        text = page['text']
        start = text.casefold().find(phrase.casefold())
        if start >= 0:
            hits.append({'page':page['page'], 'start':start,
                         'excerpt':text[max(0,start-80):start+len(phrase)+180]})
    if not hits:
        raise ValueError('Required query topic absent from source: '+phrase)
    return hits


def prepare(dataset, recovered, live_inventory, fire_pdf, output):
    from pypdf import PdfReader
    if output.exists():
        raise ValueError('Fresh output required')
    verify(dataset)
    recovery = json.loads((recovered/'manifest.json').read_text(encoding='utf-8'))
    live = {r['filename']:r['paper'] for r in json.loads(live_inventory.read_text(encoding='utf-8'))}
    additions = []
    for row in recovery['papers']:
        if row['state'] != 'source_recovered_extraction_pending':continue
        source = (recovered/row['text_path']).resolve()
        if not source.is_relative_to(recovered.resolve()) or file_hash(source) != row['text_sha256']:
            raise ValueError('Recovered text integrity failure')
        if file_hash(Path(row['source_path'])) != row['source_pdf_sha256']:
            raise ValueError('Recovered PDF changed')
        pages = json.loads(source.read_text(encoding='utf-8'))['pages']
        additions.append({'pdf':Path(row['source_path']), 'pages':pages,
                          'metadata':live[row['live_filename']], 'legacy_filename':row['live_filename'],
                          'identity_basis':row['identity_basis']})
    if len(additions) != 5:
        raise ValueError('Expected five previously recovered sources')
    reader = PdfReader(fire_pdf)
    pages = [{'page':i+1,'text':page.extract_text() or ''} for i,page in enumerate(reader.pages)]
    fire_hits = require_source_phrase(pages, 'VLFFD')
    additions.append({'pdf':fire_pdf, 'pages':pages,
        'metadata':{'title':'Intelligent video-based fire detection: A novel dataset and real-time multi-stage classification approach'},
        'legacy_filename':None, 'identity_basis':'curated_source_for_question38_not_proven_original_UUID_upload'})
    digests = [file_hash(a['pdf']) for a in additions]
    if len(set(digests)) != 6:
        raise ValueError('Duplicate supplemental PDF')
    curla = [a for a in additions if a['pdf'].name == '2501.04982.pdf']
    if len(curla) != 1:raise ValueError('Unique CuRLA source required')
    curla_hits = require_source_phrase(curla[0]['pages'], 'CuRLA')
    output.mkdir(parents=True)
    corpus = output/'corpus';corpus.mkdir()
    for path in sorted((dataset/'corpus').glob('*.json')):shutil.copy2(path, corpus/path.name)
    records = []
    for addition, digest in zip(additions, digests):
        filename = 'supplement_'+digest[:20]+'.json'
        document = {'filename':addition['pdf'].name, 'title':addition['metadata'].get('title',''),
                    'abstract':addition['metadata'].get('abstract',''),
                    'sections':[{'section_title':f"PDF page {p['page']}", 'category':'pdf_page',
                                 'page':p['page'],'content':p['text']} for p in addition['pages']],
                    'provenance':{'pdf_sha256':digest,'source_path':str(addition['pdf'].resolve()),
                                  'parser':'pypdf plain text; historical482 uses its existing parser',
                                  'metadata_status':'not_independently_validated'}}
        atomic_json(corpus/filename, document)
        records.append({'corpus_file':filename, 'pdf_sha256':digest, 'source_path':str(addition['pdf'].resolve()),
                        'legacy_filename':addition['legacy_filename'], 'identity_basis':addition['identity_basis'],
                        'historical_extraction_available':False})
    atomic_json(output/'question_source_checks.json', {
        'question37':{'topic':'CuRLA','source_pdf_sha256':file_hash(curla[0]['pdf']),'literal_topic_evidence':curla_hits},
        'question38':{'topic':'VLFFD','source_pdf_sha256':file_hash(fire_pdf),'literal_topic_evidence':fire_hits},
        'status':'Topic/source availability only; not validation of reference answers or all45question coverage',
        'questions_unchanged':True})
    shutil.copy2(dataset/'questions.py',output/'questions.py')
    files = [{'path':p.relative_to(output).as_posix(),'sha256':file_hash(p)} for p in sorted(corpus.glob('*.json'))]
    manifest = {'status':'source_only_extraction_and_indices_pending', 'documents':len(files),
                'historical_documents':482,'supplemental_documents':6,'additions':records,
                'parent_frozen_manifest_sha256':file_hash(dataset/'manifest.json'),
                'questions_sha256':file_hash(output/'questions.py'),'files':files,
                'unresolved_live_nodes_excluded_from_this_source_corpus':[
                    'dc777e4f-e513-4d2c-9827-e1bc2415162d.pdf','8a7091ff-654a-4b55-b684-7f998942645b.pdf'],
                'live_graph_modified':False,'api_calls':0,'benchmark_ready':False,
                'code_sha256':file_hash(Path(__file__)),
                'limits':'New source corpus488; not identical to historical live489. One new fire source is selected to retain question38. No expert answer validation, extraction, normalization or matched baseline rebuild completed for supplements.'}
    if len(files) != 488:raise ValueError('Unexpected source count')
    atomic_json(output/'manifest.json', manifest)
    verify(dataset)
    print(json.dumps({'documents':488,'supplements':6,'question37_topic_verified':True,
                      'question38_topic_verified':True,'api_calls':0,'benchmark_ready':False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','recovered','live-inventory','fire-pdf','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    prepare(**vars(parser.parse_args()))
