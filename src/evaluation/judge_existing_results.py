import csv
import json
import argparse
import os
import sys
from pathlib import Path

from run_baseline_comparison import (
    BACKEND_DIR,
    OUTPUT_DIR,
    average,
    cache_save,
    judge_answer,
    load_backend_modules,
    parse_judge_output,
    format_text_context,
)


RESULT_PATH = OUTPUT_DIR / "comparison_results.jsonl"
CSV_PATH = OUTPUT_DIR / "comparison_results.csv"
SUMMARY_PATH = OUTPUT_DIR / "comparison_summary.json"
LATEX_PATH = OUTPUT_DIR / "comparison_table.tex"


def load_openai_config():
    """Load OpenAI key/model from backend config.py without printing secrets."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        import config
    except Exception:
        return None

    key = getattr(config, "OPENAI_API_KEY", None)
    model = getattr(config, "OPENAI_JUDGE_MODEL", None)
    if key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = key
    return model


def contexts_from_saved(text: str):
    try:
        items = json.loads(text or "[]")
    except Exception:
        return []
    contexts = []
    for item in items:
        contexts.append(
            {
                "paper_id": item.get("paper_id"),
                "title": item.get("paper_title") or item.get("title"),
                "section_name": item.get("section"),
                "text": item.get("content") or item.get("text") or "",
            }
        )
    return contexts


def judge_answer_openai(question: str, reference: str, answer: str, contexts, model: str):
    from openai import OpenAI

    client = OpenAI()
    prompt = f"""
You are an impartial evaluator for retrieval-augmented scientific question answering.
Score each metric from 0.0 to 1.0.

Definitions:
- faithfulness: the generated answer is supported by the retrieved context.
- relevancy: the generated answer directly answers the question.
- context_precision: retrieved contexts are mostly relevant and not noisy.
- context_recall: retrieved contexts contain enough evidence to answer the reference answer.

Question: {question}
Reference answer: {reference}
Generated answer: {answer}
Retrieved context:
{format_text_context(contexts, max_chars_per_context=700)}

Return one minified JSON object only. No Markdown. No explanation. Use exactly these keys:
{{"faithfulness":0.0,"relevancy":0.0,"context_precision":0.0,"context_recall":0.0,"unsupported_answer":false,"controlled_refusal":false}}
""".strip()

    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )
    return parse_judge_output(response.output_text)


def openai_error_status(exc: Exception) -> str:
    text = str(exc)
    if "insufficient_quota" in text or "RateLimitError" in text or "429" in text:
        return "QUOTA"
    if "model_not_found" in text or "does not exist" in text or "404" in text:
        return "MODEL_NOT_FOUND"
    if "invalid_api_key" in text or "Incorrect API key" in text or "401" in text:
        return "INVALID_KEY"
    return "ERROR"


def judge_answer_openai_auto(question: str, reference: str, answer: str, contexts, models):
    last_error = None
    attempted = []
    for model in models:
        if not model or model in attempted:
            continue
        attempted.append(model)
        try:
            result = judge_answer_openai(question, reference, answer, contexts, model)
            result["judge_model_used"] = model
            return result
        except Exception as exc:
            last_error = exc
            status = openai_error_status(exc)
            if status in {"QUOTA", "MODEL_NOT_FOUND", "ERROR"}:
                continue
            raise
    raise RuntimeError(
        "All OpenAI judge models failed: "
        + ", ".join(attempted)
        + f". Last error: {last_error}"
    )


def write_outputs(rows):
    methods = ["Lexical BM25 RAG", "Vector RAG", "Proposed KG-RAG"]
    RESULT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    fieldnames = [
        "question_id",
        "method",
        "faithfulness",
        "relevancy",
        "context_precision",
        "context_recall",
        "retrieval_time",
        "generation_time",
        "total_time",
        "unsupported_answer",
        "controlled_refusal",
        "question",
        "reference_answer",
        "generated_answer",
        "retrieved_context",
        "error",
        "notes",
        "judge_model",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for method in methods:
        group = [r for r in rows if r.get("method") == method]
        if not group:
            continue
        summary.append(
            {
                "Method": method,
                "N": len(group),
                "Faithfulness": average(r.get("faithfulness") for r in group),
                "Relevancy": average(r.get("relevancy") for r in group),
                "Context Precision": average(r.get("context_precision") for r in group),
                "Context Recall": average(r.get("context_recall") for r in group),
                "Latency (s)": average(r.get("total_time") for r in group),
                "Unsupported": sum(1 for r in group if r.get("unsupported_answer") is True),
                "Controlled Refusal": sum(1 for r in group if r.get("controlled_refusal") is True),
            }
        )
    cache_save(SUMMARY_PATH, summary)

    def fmt(x):
        return "--" if x is None else f"{x:.3f}"

    lines = [
        r"\begin{table}[H]",
        r"\caption{Comparison of retrieval-augmented question-answering methods on 45 queries.}",
        r"\label{tab:baselinecomparison}",
        r"\centering",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lccccc@{}}",
        r"\toprule",
        r"\textbf{Method} & \textbf{Faith.} & \textbf{Relev.} & \textbf{Ctx. P} & \textbf{Ctx. R} & \textbf{Latency (s)} \\",
        r"\midrule",
    ]
    for s in summary:
        lines.append(
            f"{s['Method']} & {fmt(s['Faithfulness'])} & {fmt(s['Relevancy'])} & "
            f"{fmt(s['Context Precision'])} & {fmt(s['Context Recall'])} & {fmt(s['Latency (s)'])} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular*}", r"\end{table}", ""])
    LATEX_PATH.write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-model", default="")
    parser.add_argument("--provider", choices=["gemini", "openai"], default="gemini")
    parser.add_argument("--reset", action="store_true", help="Reset existing metric fields before judging")
    parser.add_argument(
        "--fallback-models",
        default="gpt-5.5,gpt-5.1,gpt-5,gpt-4.1,gpt-4o,o4-mini,gpt-4o-mini",
        help="Comma-separated OpenAI model fallback list for judge",
    )
    args = parser.parse_args()

    client = types = None
    if args.provider == "openai":
        config_model = load_openai_config()
        if not args.judge_model:
            args.judge_model = config_model or "gpt-5.5"
        fallback_models = [args.judge_model] + [
            item.strip() for item in args.fallback_models.split(",") if item.strip()
        ]
    else:
        if not args.judge_model:
            args.judge_model = "gemini-3-flash-preview"
        client, types = load_backend_modules()
    rows = [json.loads(line) for line in RESULT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.reset:
        metric_keys = [
            "faithfulness",
            "relevancy",
            "context_precision",
            "context_recall",
            "unsupported_answer",
            "controlled_refusal",
            "notes",
        ]
        for row in rows:
            for key in metric_keys:
                row[key] = None
            row["judge_model"] = None
        write_outputs(rows)
    pending = [i for i, r in enumerate(rows) if r.get("faithfulness") is None and not r.get("error")]
    print(f"Rows: {len(rows)}; pending judge: {len(pending)}", flush=True)
    for n, idx in enumerate(pending, 1):
        row = rows[idx]
        print(f"[{n}/{len(pending)}] judge q{row['question_id']} - {row['method']}", flush=True)
        contexts = contexts_from_saved(row.get("retrieved_context", ""))
        try:
            if args.provider == "openai":
                judge = judge_answer_openai_auto(
                    row.get("question", ""),
                    row.get("reference_answer", ""),
                    row.get("generated_answer", ""),
                    contexts,
                    models=fallback_models,
                )
            else:
                judge = judge_answer(
                    client,
                    types,
                    row.get("question", ""),
                    row.get("reference_answer", ""),
                    row.get("generated_answer", ""),
                    contexts,
                    model=args.judge_model,
                )
        except Exception as exc:
            judge = {
                "faithfulness": None,
                "relevancy": None,
                "context_precision": None,
                "context_recall": None,
                "unsupported_answer": None,
                "controlled_refusal": None,
                "notes": f"judge_failed: {exc}",
            }
        row.update(judge)
        row["judge_model"] = judge.get("judge_model_used", args.judge_model)
        rows[idx] = row
        write_outputs(rows)
    summary = write_outputs(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
