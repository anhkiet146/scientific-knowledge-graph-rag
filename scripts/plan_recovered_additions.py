"""Prepare page-preserving extraction tasks for recovered sources, without API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/extraction'))
from workflow_io import atomic_json, file_hash
from task_plan import plan


def prepare(recovered, inventory, output):
    if output.exists():
        raise ValueError('Fresh output required')
    manifest = json.loads((recovered / 'manifest.json').read_text(encoding='utf-8'))
    live = {r['filename']:r['paper'] for r in json.loads(inventory.read_text(encoding='utf-8'))}
    prepared = []
    for row in manifest['papers']:
        if row['state'] != 'source_recovered_extraction_pending':
            continue
        source = (recovered / row['text_path']).resolve()
        if not source.is_relative_to(recovered.resolve()) or file_hash(source) != row['text_sha256']:
            raise ValueError('Recovered text changed or path outside source folder')
        data = json.loads(source.read_text(encoding='utf-8'))
        pages = data['pages']
        if [p['page'] for p in pages] != list(range(1, len(pages)+1)):
            raise ValueError('Page sequence invalid')
        meta = live[row['live_filename']]
        document = {'filename':row['live_filename'], 'title':meta.get('title',''),
                    'abstract':meta.get('abstract',''),
                    'sections':[{'section_title':f"PDF page {p['page']}", 'category':'pdf_page',
                                 'page':p['page'], 'content':p['text']} for p in pages],
                    'source_pdf_sha256':row['source_pdf_sha256'],
                    'source_text_sha256':row['text_sha256'],
                    'metadata_status':'legacy_metadata_unverified_do_not_treat_as_gold'}
        tasks = plan(document, 100)
        name = Path(row['live_filename']).stem + '.json'
        prepared.append((name, document, tasks))
    output.mkdir(parents=True)
    rows = []
    for name, document, tasks in prepared:
        atomic_json(output / 'documents' / name, document)
        atomic_json(output / 'plans' / name, tasks)
        rows.append({'file':name, 'tasks':len(tasks['tasks']),
                     'evidence_items':len(tasks['catalog']['items']),
                     'max_task_input_characters':max((t['input_characters'] for t in tasks['tasks']), default=0),
                     'document_sha256':file_hash(output/'documents'/name),
                     'plan_sha256':file_hash(output/'plans'/name)})
    result = {'status':'offline_plan_not_extraction', 'documents':rows,
              'planned_initial_api_calls':sum(r['tasks'] for r in rows), 'actual_api_calls':0,
              'recovery_manifest_sha256':file_hash(recovered/'manifest.json'),
              'code_sha256':file_hash(Path(__file__)),
              'unresolved_sources':[r['live_filename'] for r in manifest['papers'] if r['state']=='unresolved'],
              'limits':'Five recovered PDFs only. Task count is not a complete489 budget. No historical extraction recovered. Page text can contain references, layout errors and table ambiguity; tasks require source/semantic review and token preflight before execution.'}
    atomic_json(output/'manifest.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('recovered','inventory','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    prepare(**vars(parser.parse_args()))
