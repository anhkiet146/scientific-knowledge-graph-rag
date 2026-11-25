"""Offline postfilter ablation on fixed verdicts and same-input normalization."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import shutil
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src/retrieval'),str(ROOT/'src/extraction')]
from verifier_policies import POLICIES,verifier_policy
from workflow_io import atomic_json,canonical_hash,file_hash,read_json


def readlines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def partition(mapping):
    groups=defaultdict(set)
    for key,value in mapping.items():
        groups[value].add(key)
    return {frozenset(v) for v in groups.values()}


def run(fixtures,pilot,control,normalized,output):
    if output.exists():
        raise ValueError('Fresh output required')
    fixture_manifest=read_json(fixtures/'manifest.json')
    fixture=fixtures/'synthetic_cases.jsonl'
    if file_hash(fixture)!=fixture_manifest['cases_sha256']:
        raise ValueError('Fixture changed')
    cases=[dict(case_id=r['case_id'],group=r['group'],draft=r['draft'],
                contexts=r['contexts'],verdict=r['verdict'],source_kind='developer_fixture')
           for r in readlines(fixture)]
    sources=[fixture,fixtures/'manifest.json']
    contexts=read_json(pilot/'selected_contexts.json')
    kg_context=contexts['kg']
    if canonical_hash(kg_context['context_json'])!=kg_context['context_sha256']:
        raise ValueError('Saved context hash mismatch')
    if json.loads(kg_context['context_json'])!=kg_context['context']:
        raise ValueError('Saved context serialization mismatch')
    for file in sorted((pilot/'records').glob('r*_kg_verified.json')):
        verified=read_json(file)
        draft_file=pilot/'records'/verified['paired_kg_record']
        draft=read_json(draft_file)
        if verified['context_sha256']!=kg_context['context_sha256'] or draft['context_sha256']!=verified['context_sha256']:
            raise ValueError('Unpaired saved context')
        if verified['draft_answer']!=draft['draft_answer']:
            raise ValueError('Unpaired saved draft')
        claims=[{k:r[k] for k in ['text','quote','context_index','supported','atomic'] if k in r}
                for r in verified['claim_audit']]
        cases.append(dict(case_id=file.stem,group='historical_fixed_verdict',
                          source_kind='saved_claim_audit_not_new_model_verdict',
                          draft=draft['draft_answer'],contexts=kg_context['context'],
                          verdict={'claims':claims},
                          atomic_field_available=all('atomic' in r for r in claims)))
        sources.extend([file,draft_file])
    if len({r['case_id'] for r in cases})!=len(cases):
        raise ValueError('Duplicate replay case')
    a,b=read_json(control/'manifest.json'),read_json(normalized/'manifest.json')
    if a['source_files_sha256']!=b['source_files_sha256']:
        raise ValueError('Normalization comparison input drift')
    if a['surface_policy']!='paper_surface_v1' or b['surface_policy']!='paper_literal_v2':
        raise ValueError('Unexpected normalization policies')
    sa,sb=read_json(control/'summary.json'),read_json(normalized/'summary.json')
    ma,mb=read_json(control/'identity_maps.json'),read_json(normalized/'identity_maps.json')
    entities=readlines(normalized/'entities.jsonl')
    normalization=dict(source_hashes_equal=True,papers=sa['papers'],
        entities=sa['entity_occurrences'],relations=sa['relation_occurrences'],
        grouping_partitions_equal=partition(ma['surface'])==partition(mb['surface']),
        control_graph=sa['structural_comparison']['surface'],
        literal_graph=sb['structural_comparison']['surface'],
        names_with_compatibility_normalization_change=sum(
            unicodedata.normalize('NFKC',r['name'])!=unicodedata.normalize('NFC',r['name']) for r in entities),
        limits='Different technical node IDs are not counted as changed grouping. Same structure does not prove correct identity, synonym recall or QA impact.')
    output.mkdir(parents=True)
    results=[];summary=defaultdict(Counter)
    for case in cases:
        for policy in POLICIES:
            answer,audit=verifier_policy(policy)[1](case['draft'],case['contexts'],case['verdict'])
            accepted=sum(bool(r['accepted']) for r in audit)
            results.append(dict(case_id=case['case_id'],group=case['group'],policy=policy,
                                answer=answer,accepted_claims=accepted,audit=audit,
                                atomic_field_available=case.get('atomic_field_available'),
                                source_kind=case['source_kind']))
            summary[policy][case['group']+'_cases_with_acceptance']+=bool(accepted)
            summary[policy][case['group']+'_accepted_claims']+=accepted
    with (output/'postfilter_replay.jsonl').open('w',encoding='utf-8') as stream:
        for row in results:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    atomic_json(output/'summary.json',dict(cases=len(cases),groups=dict(Counter(c['group'] for c in cases)),
        policies=list(POLICIES),fixed_verdict_results={k:dict(v) for k,v in summary.items()},
        normalization=normalization,api_calls=0,independent_labels_created=False,quality_scores_computed=False,
        limits='Postfilter replay holds drafts, evidence and verdicts fixed; no new policy-specific LLM verdicts. Developer controls are not independent gold. Missing atomic declarations in historical verdicts remain missing and are not repaired. Strict value copying can reject correct paraphrases, lists and incomplete draft answers. Source values can still contain extraction errors or contradict other context.'))
    code=[Path(__file__),*[ROOT/'src/retrieval'/name for name in
          ['claim_verification.py','claim_verification_experimental.py','claim_verification_literal.py','verifier_policies.py']]]
    sources += [pilot/'selected_contexts.json',control/'manifest.json',normalized/'manifest.json',
                control/'summary.json',normalized/'summary.json',control/'identity_maps.json',normalized/'identity_maps.json']
    atomic_json(output/'manifest.json',dict(inputs={str(p.resolve()):file_hash(p) for p in sources},
        code_sha256={p.name:file_hash(p) for p in code},normalization_manifest_hashes_equal=False,
        normalization_source_content_hashes_equal=True,postfilter_only=True))
    for file in code:
        shutil.copy2(file,output/file.name)
    print(json.dumps(dict(cases=len(cases),fixed_verdict_results={k:dict(v) for k,v in summary.items()},normalization=normalization),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ['fixtures','pilot','control','normalized','output']:
        parser.add_argument('--'+field,type=Path,required=True)
    run(**vars(parser.parse_args()))
