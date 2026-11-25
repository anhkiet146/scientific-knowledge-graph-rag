"""Offline development evidence only; never calls an LLM or creates gold labels."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/extraction')]
from workflow_io import read_json,atomic_json
from chunk_runner import run


def main():
    output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=True)
    schema=read_json(ROOT/'schemas/extracted_kg_strict_v3.schema.json')
    schema['title']='Strict v3.1 materialized extraction with source names'
    entity=schema['properties']['entities']['items']
    entity['properties']['name']={'type':'string','minLength':1,'maxLength':2048}
    if 'name' not in entity['required']:entity['required'].append('name')
    atomic_json(ROOT/'schemas/extracted_kg_strict_v3_1.schema.json',schema)
    spec=importlib.util.spec_from_file_location('chunk_test_fixture',ROOT/'tests/test_chunk_execution.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    case=module.ChunkExecutionTests();case.setUp()
    demo=output/'synthetic_demo'
    if demo.exists():raise ValueError('Use a fresh evidence output directory')
    demo.mkdir();args,key=case.fixtures(demo)
    # Deliberately synthetic completion fixtures: exercise transport, not scientific recall.
    stopped=run(args);partial=read_json(args.output/'papers'/(key+'.json'))
    atomic_json(output/'partial_candidate.json',partial)
    args.max_tasks=0;resumed=run(args)
    final=read_json(args.output/'papers'/(key+'.json'))
    atomic_json(output/'offline_verification.json',{'fixture_type':'synthetic transport fixture, not model output or gold',
        'stop_exit_code':stopped,'resume_exit_code':resumed,'partial_status':partial['candidate_status'],
        'final_status':final['candidate_status'],'completed_tasks':len(final['execution_coverage']['completed_tasks']),
        'actual_api_calls':0,'graph_writes':0,'scientific_accuracy_established':False})


if __name__=='__main__':main()
