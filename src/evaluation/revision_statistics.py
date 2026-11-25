"""Question-level paired inference; repeated runs are not independent questions."""
import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

METRICS = ("faithfulness", "relevancy", "context_precision", "context_recall", "total_time")


def load_jsonl(path):
    # JSON strings may legally contain U+2028/U+2029. Only LF delimits records.
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def percentile(values, q):
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo = int(pos)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (pos - lo)


def paired_inference(differences, seed=20261111, draws=10000):
    if not differences:
        return {"n_questions": 0}
    rng = random.Random(seed)
    n = len(differences)
    mean = statistics.mean(differences)
    bootstrap = [statistics.mean(rng.choices(differences, k=n)) for _ in range(draws)]
    if all(x == 0 for x in differences):
        p = 1.0
    elif n <= 16:
        p = sum(abs(sum(d * (1 if mask & (1 << i) else -1)
                        for i, d in enumerate(differences)) / n) >= abs(mean) - 1e-12
                for mask in range(1 << n)) / (1 << n)
    else:
        extreme = sum(abs(sum(d * rng.choice((-1, 1)) for d in differences) / n)
                      >= abs(mean) - 1e-12 for _ in range(draws))
        p = (extreme + 1) / (draws + 1)
    result = dict(n_questions=n, mean_difference=mean,
                  bootstrap_95_ci=[percentile(bootstrap, .025), percentile(bootstrap, .975)],
                  paired_sign_flip_p=p)
    try:
        from scipy.stats import wilcoxon
        result["wilcoxon_p"] = float(wilcoxon(differences).pvalue) if any(differences) else 1.0
    except ImportError:
        result["wilcoxon_p"] = None
    return result


def summarize(rows, reference="kg", draws=10000):
    rows = list(rows)
    seen = set()
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["method"], row["question_id"], row["repeat"])
        if key in seen:
            raise ValueError(f"Duplicate method/question/repeat: {key}")
        seen.add(key)
        if row.get("error"):
            continue
        for metric in METRICS:
            value = row.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                grouped[(row["method"], metric)][row["question_id"]].append(value)
    summaries, tests = [], []
    for (method, metric), by_question in sorted(grouped.items()):
        qmeans = {q: statistics.mean(v) for q, v in by_question.items()}
        summaries.append(dict(method=method, metric=metric, n_questions=len(qmeans),
                              n_observations=sum(map(len, by_question.values())),
                              mean=statistics.mean(qmeans.values()),
                              sd_between_questions=statistics.stdev(qmeans.values()) if len(qmeans) > 1 else None,
                              mean_within_question_sd=statistics.mean([statistics.stdev(v) for v in by_question.values() if len(v)>1]) if any(len(v)>1 for v in by_question.values()) else None))
        if method == reference:
            continue
        base = grouped.get((reference, metric), {})
        common = sorted(set(base) & set(by_question), key=str)
        diffs = [statistics.mean(base[q]) - qmeans[q] for q in common]
        tests.append(dict(reference=reference, comparator=method, metric=metric,
                          **paired_inference(diffs, draws=draws)))
    # Holm correction across all reported comparisons/metrics, including latency.
    ordered = sorted([t for t in tests if t.get("n_questions")], key=lambda t:t["paired_sign_flip_p"])
    previous = 0.0
    for index, test in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered)-index)*test["paired_sign_flip_p"]))
        test["holm_adjusted_p"] = previous
    return {"analysis_scope": "conditional-success; failed rows excluded from quality/latency estimates",
            "unit_of_inference": "question; repeats averaged within question",
            "difference_direction": "reference minus comparator; lower latency is better",
            "execution_counts": [dict(method=method,
                n_rows=sum(r["method"]==method for r in rows),
                n_failed=sum(r["method"]==method and bool(r.get("error")) for r in rows))
                for method in sorted({r["method"] for r in rows})],
            "summary": summaries, "paired_tests": tests}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("results",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    rows=load_jsonl(args.results)
    args.output.write_text(json.dumps(summarize(rows),ensure_ascii=False,indent=2),encoding="utf-8")
