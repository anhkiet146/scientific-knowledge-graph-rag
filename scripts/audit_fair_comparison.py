"""Fail closed before QA when retrieval inputs or runtime conditions differ."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/extraction'))
from workflow_io import atomic_json,read_json,file_hash,loads,canonical_hash


def audit(protocol,bundles):
    issues=[]
    for method in protocol['context_methods']:
        row=bundles.get(method)
        if row is None:
            issues.append({'method':method,'reason':'method_not_ready'});continue
        if row.get('state')!='contexts_frozen':issues.append({'method':method,'reason':'contexts_not_frozen'})
        for field,expected in protocol['shared_inputs'].items():
            if row.get(field)!=expected:
                issues.append({'method':method,'reason':'shared_input_mismatch','field':field,
                               'expected':expected,'observed':row.get(field)})
        if row.get('questions')!=45 or row.get('context_records')!=45:
            issues.append({'method':method,'reason':'incomplete_question_grid'})
        if 'cache_policy' in protocol and row.get('cache_policy')!=protocol['cache_policy']:
            issues.append({'method':method,'reason':'cache_policy_mismatch'})
        if method in protocol['shared_dense_methods']:
            for field,expected in protocol['dense_conditions'].items():
                if row.get('dense',{}).get(field)!=expected:
                    issues.append({'method':method,'reason':'dense_condition_mismatch','field':field,
                        'expected':expected,'observed':row.get('dense',{}).get(field)})
        if method=='lightrag' and row.get('released_implementation')!=protocol['released_sota']:
            issues.append({'method':method,'reason':'released_sota_not_verified'})
    return {'status':'blocked' if issues else 'ready_for_controlled_generation',
            'issues':issues,'quality_comparison_complete':False,'api_calls':0,
            'limits':'Input readiness only. Passing does not prove runtime compliance, answer quality, independent grading or completed repetitions.'}


def verified_contexts(protocol,bundles,encode):
    result=audit(protocol,bundles);contexts=[];hardware=None
    for method in protocol['context_methods']:
        bundle=bundles.get(method)
        if bundle is None:continue
        try:
            path=Path(bundle['context_artifact'])
            if file_hash(path)!=bundle['context_artifact_sha256']:raise ValueError('Context artifact hash mismatch')
            selected=[loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
            selected=[r for r in selected if r['method']==method]
            ids=[r['question_id'] for r in selected]
            if any(type(i) is not int for i in ids) or sorted(ids)!=list(range(1,46)):raise ValueError('Actual question grid mismatch')
            selected.sort(key=lambda r:r['question_id'])
            for row in selected:
                text=row['context_json']
                if loads(text)!=row['context'] or canonical_hash(text)!=row['context_sha256']:raise ValueError('Context serialization changed')
                count=len(encode(text))
                if count!=row['context_tokens'] or count>protocol['shared_inputs']['context_limit_tokens']:raise ValueError('Actual token budget mismatch')
                if protocol['shared_inputs']['scope_policy']=='whole_corpus' and row.get('paper_scope',{}).get('allowed_papers') is not None:
                    raise ValueError('Actual context uses restricted paper scope')
            for field,key in [('question_sha256','question'),('query_sha256','shared_query')]:
                if canonical_hash([(r['question_id'],r[key]) for r in selected])!=protocol['shared_inputs'][field]:raise ValueError('Actual query/question differs')
            manifest=read_json(Path(bundle['artifact_manifest']))
            if file_hash(Path(bundle['artifact_manifest']))!=bundle['artifact_manifest_sha256']:raise ValueError('Artifact manifest changed')
            if manifest.get('contexts_sha256')!=file_hash(path):raise ValueError('Context artifact is not bound to manifest')
            if manifest.get('corpus_sha256',manifest.get('dataset_manifest_sha256'))!=protocol['shared_inputs']['corpus_sha256']:
                raise ValueError('Artifact corpus differs')
            if 'cache_policy' in protocol and manifest.get('cache_policy')!=protocol['cache_policy']:
                raise ValueError('Artifact cache policy differs')
            runtime_path=Path(bundle['runtime_artifact'])
            if file_hash(runtime_path)!=bundle['runtime_artifact_sha256']:raise ValueError('Runtime receipt changed')
            if manifest.get('runtime_sha256')!=file_hash(runtime_path):raise ValueError('Runtime receipt is not bound to manifest')
            if method in protocol['shared_dense_methods'] and manifest.get('dense')!=protocol['dense_conditions']:
                raise ValueError('Actual dense manifest differs')
            runtime=read_json(runtime_path);limit=protocol['dense_conditions']['threads']
            if runtime['device']!='cpu' or runtime['thread_limit']!=limit or runtime['torch_threads']!=limit:
                raise ValueError('Runtime CPU conditions differ')
            if any(pool['num_threads']>limit for pool in runtime['thread_pools']):raise ValueError('BLAS/OpenMP thread limit differs')
            if any(pool['num_threads']>limit for pool in runtime['thread_pools_after']):raise ValueError('Final BLAS/OpenMP thread limit differs')
            observed={key:runtime[key] for key in ('platform','machine','processor','logical_cpus')}
            if hardware is not None and hardware!=observed:raise ValueError('Hardware conditions differ')
            hardware=observed
            contexts.extend(selected)
        except (KeyError,ValueError,OSError,TypeError) as exc:
            result['issues'].append({'method':method,'reason':'artifact_verification_failed','exception_type':type(exc).__name__})
    result['status']='blocked' if result['issues'] else 'ready_for_controlled_generation'
    result['verified_context_records']=len(contexts)
    result['verified_context_methods']=sorted({r['method'] for r in contexts})
    return result,contexts


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','bundles','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh output required')
    result=audit(read_json(args.protocol),read_json(args.bundles))
    result['protocol_sha256']=file_hash(args.protocol)
    result['bundles_sha256']=file_hash(args.bundles)
    atomic_json(args.output,result)
    print(result['status'],len(result['issues']),'blocking conditions')
