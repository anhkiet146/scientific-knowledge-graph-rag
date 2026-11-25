"""Explicit complete-grid utility; never infer labels or zero-fill missing runs."""
import itertools
import argparse
import json
import math
import statistics
import random
from collections import defaultdict
from pathlib import Path
try:
    from .revision_statistics import paired_inference
except ImportError:
    from revision_statistics import paired_inference


def question_mean_ci(values,draws,seed=20261116):
    rng=random.Random(seed)
    means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(draws))
    def percentile(q):
        position=(len(means)-1)*q;index=int(position)
        return means[index]+(means[min(index+1,len(means)-1)]-means[index])*(position-index)
    return [percentile(.025),percentile(.975)]


def summarize(rows,*,methods,question_ids,repeats,reference='kg',metrics=('correctness',),draws=2000):
    if any(not isinstance(m,str) or not m.strip() for m in list(methods)+list(metrics)):
        raise ValueError('Method and metric names required')
    if any(type(v) is not int or v<1 for v in list(question_ids)+list(repeats)):
        raise ValueError('Positive integer question/repeat IDs required')
    for values in (methods,question_ids,repeats,metrics):
        if not values or len(set(values))!=len(values):raise ValueError('Nonempty unique expected grid required')
    if reference not in methods or type(draws) is not int or draws<100:raise ValueError('Invalid reference or bootstrap draws')
    if any(m in {'total_time','latency','attempt_seconds'} for m in metrics):raise ValueError('Quality and latency are separate')
    expected=set(itertools.product(methods,question_ids,repeats));seen=set();scores=defaultdict(list)
    successful=defaultdict(list);counts={m:{'success':0,'failed':0} for m in methods}
    timing={m:{'success':[],'failed':[]} for m in methods};sources=set()
    for row in rows:
        if type(row.get('question_id')) is not int or type(row.get('repeat')) is not int:
            raise ValueError('Run IDs must be integers, not boolean or float aliases')
        key=(row['method'],row['question_id'],row['repeat'])
        if key not in expected or key in seen:raise ValueError('Unexpected or duplicate run')
        seen.add(key);status=row.get('generation_status');method=key[0]
        if status not in {'success','failed'}:raise ValueError('Explicit generation status required; error provenance cannot be inferred')
        seconds=row.get('attempt_seconds')
        if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:
            raise ValueError('Observed attempt duration required, including failures')
        counts[method][status]+=1;timing[method][status].append(seconds)
        if status=='success':
            source=row.get('assessment_source')
            if source not in {'independent_human','llm_proxy'}:raise ValueError('Explicit assessment provenance required')
            sources.add(source)
        for metric in metrics:
            if status=='failed':value=0.0
            else:
                value=row.get(metric)
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
                    raise ValueError('Successful generation requires an observed [0,1] quality score')
                successful[(method,metric)].append(value)
            scores[(method,metric,key[1])].append(value)
    if seen!=expected:raise ValueError('Incomplete repeat grid; missing rows are not failed generations')
    if len(sources)>1:raise ValueError('Do not pool human and proxy judgments')
    summary=[];tests=[]
    for method in methods:
        for metric in metrics:
            qmeans=[statistics.mean(scores[(method,metric,q)]) for q in question_ids]
            observed=successful[(method,metric)]
            summary.append({'method':method,'metric':metric,'failure_penalized_mean':statistics.mean(qmeans),
                'n_questions':len(question_ids),'repeats_per_question':len(repeats),
                'bootstrap_95_ci_failure_penalized_mean':question_mean_ci(qmeans,draws),
                'sd_between_questions':statistics.stdev(qmeans) if len(qmeans)>1 else None,
                'mean_within_question_sd':statistics.mean(statistics.stdev(scores[(method,metric,q)]) for q in question_ids) if len(repeats)>1 else None,
                'conditional_success_mean':statistics.mean(observed) if observed else None,
                'conditional_success_unit':'observed successful run, not a paired effect estimate',
                'success_coverage':counts[method]['success']/(len(question_ids)*len(repeats))})
            if method!=reference:
                differences=[statistics.mean(scores[(reference,metric,q)])-statistics.mean(scores[(method,metric,q)]) for q in question_ids]
                tests.append({'reference':reference,'comparator':method,'metric':metric,**paired_inference(differences,draws=draws)})
    ordered=sorted(tests,key=lambda t:t['paired_sign_flip_p']);previous=0.
    for index,test in enumerate(ordered):
        previous=max(previous,min(1.,(len(ordered)-index)*test['paired_sign_flip_p']));test['holm_adjusted_p']=previous
    return {'analysis_scope':'complete-grid; explicit failed generation quality=0; missing runs rejected',
        'unit_of_inference':'question, averaging repeats within question','assessment_source':next(iter(sources),None),
        'resampling':{'unit':'question mean across declared repeats','draws':draws,'mean_ci_seed':20261116,
            'mean_ci_method':'percentile bootstrap; not a new independent test sample',
            'multiplicity':'Holm over the declared method-by-metric paired sign-flip family; Wilcoxon is supplementary'},
        'counts':counts,'summary':summary,'paired_tests':tests,
        'attempt_timing':{m:{s:{'n':len(v),'mean_seconds':statistics.mean(v) if v else None} for s,v in by_status.items()} for m,by_status in timing.items()},
        'limitations':'Requires new explicit status and score provenance; incompatible legacy errors are not reinterpreted. Not an experiment result by itself.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True);parser.add_argument('--design',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh analysis output required')
    design=json.loads(args.design.read_text(encoding='utf-8'))
    if set(design)!={'methods','question_ids','repeats','reference','metrics'}:raise ValueError('Explicit expected design required')
    rows=[json.loads(line) for line in args.records.read_text(encoding='utf-8').split('\n') if line.strip()]
    result=summarize(rows,**design)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
