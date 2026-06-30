import argparse
import ast
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


WORKSPACE = Path(__file__).resolve().parent
OUTPUT_DIR = WORKSPACE / "outputs" / "baseline_comparison"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LLM_ROOT = Path(r"E:\LLM")
BACKEND_DIR = LLM_ROOT / "knowledge-extraction" / "backend"
DATA_JSON_DIR = LLM_ROOT / "data" / "json"
TEST_SET_FILE = LLM_ROOT / "scripts" / "tao_test_set_full.py"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


GENAI_POOL = None


def extract_gemini_keys() -> List[str]:
    keys: List[str] = []

    def add(value: str):
        value = (value or "").strip().strip('"').strip("'")
        if value and value not in keys:
            keys.append(value)

    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        add(os.getenv(env_name, ""))

    config_path = BACKEND_DIR / "config.py"
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"(?:GEMINI_API_KEY\s*=\s*)?[\"']([^\"']{20,})[\"']", text):
            candidate = match.group(1).strip()
            if re.match(r"^(AQ\.|AIza|ya29\.|sk-)", candidate):
                add(candidate)
        for match in re.finditer(r"#\s*([A-Za-z0-9_.\-]{20,})", text):
            candidate = match.group(1).strip()
            if re.match(r"^(AQ\.|AIza|ya29\.|sk-)", candidate):
                add(candidate)
    return keys


class RotatingGenAI:
    def __init__(self, genai_module, api_keys: List[str]):
        if not api_keys:
            raise RuntimeError("Không tìm thấy Gemini API key.")
        self.clients = [genai_module.Client(api_key=key) for key in api_keys]
        self.disabled = set()
        self.index = 0
        self.models = self.ModelRouter(self)

    class ModelRouter:
        def __init__(self, parent):
            self.parent = parent

        def generate_content(self, *args, **kwargs):
            return self.parent.generate_content(*args, **kwargs)

        def embed_content(self, *args, **kwargs):
            return self.parent.embed_content(*args, **kwargs)

    def _ordered_clients(self):
        n = len(self.clients)
        for offset in range(n):
            idx = (self.index + offset) % n
            if idx in self.disabled:
                continue
            yield idx, self.clients[idx]

    def _should_rotate(self, exc: Exception) -> bool:
        msg = str(exc)
        return (
            "429" in msg
            or "RESOURCE_EXHAUSTED" in msg
            or "503" in msg
            or "UNAVAILABLE" in msg
            or "API_KEY_INVALID" in msg
            or "API key not valid" in msg
        )

    def _disable_if_invalid(self, idx: int, exc: Exception) -> None:
        msg = str(exc)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            self.disabled.add(idx)

    def generate_content(self, *args, **kwargs):
        last_error = None
        for idx, client in self._ordered_clients():
            try:
                self.index = idx
                return client.models.generate_content(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if not self._should_rotate(exc):
                    raise
                self._disable_if_invalid(idx, exc)
                self.index = (idx + 1) % len(self.clients)
                continue
        raise last_error

    def embed_content(self, *args, **kwargs):
        last_error = None
        for idx, client in self._ordered_clients():
            try:
                self.index = idx
                return client.models.embed_content(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if not self._should_rotate(exc):
                    raise
                self._disable_if_invalid(idx, exc)
                self.index = (idx + 1) % len(self.clients)
                continue
        raise last_error


def load_backend_modules():
    from google import genai
    from google.genai import types

    global GENAI_POOL
    if GENAI_POOL is None:
        keys = extract_gemini_keys()
        GENAI_POOL = RotatingGenAI(genai, keys)
        print(f"Loaded {len(keys)} Gemini API key(s) for rotation.", flush=True)
    return GENAI_POOL, types


def load_kg_rag():
    import graphrag_engine

    if GENAI_POOL is not None:
        graphrag_engine.gemini_client = GENAI_POOL
        print("KG-RAG Gemini client patched with rotating key pool.", flush=True)

    return graphrag_engine.ask_graphrag


def ask_kg_via_http(url: str, question: str) -> Tuple[str, List[str], Dict[str, Any]]:
    payload = {
        "session_id": f"baseline-{hashlib.sha1(question.encode('utf-8')).hexdigest()[:12]}",
        "question": question,
        "scope": "all",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        obj = json.loads(resp.read().decode("utf-8"))
    return obj.get("answer", ""), obj.get("highlight_nodes", []), obj.get("timings", {})


def read_test_set(path: Path = TEST_SET_FILE) -> List[Dict[str, str]]:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "data":
                    data = ast.literal_eval(node.value)
                    return [
                        {
                            "question": item.get("question", "").strip(),
                            "reference_answer": item.get("ground_truth", "").strip(),
                            "original_chatbot_answer": item.get("chatbot_answer", "").strip(),
                            "original_context": item.get("context", "").strip(),
                        }
                        for item in data
                        if item.get("question")
                    ]
    raise RuntimeError(f"Không tìm thấy biến data trong {path}")


def clean_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def console_text(text: str) -> str:
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    return (text or "").encode(enc, errors="backslashreplace").decode(enc, errors="replace")


def tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    return re.findall(r"[a-zA-ZÀ-ỹ0-9][a-zA-ZÀ-ỹ0-9_\-./%°]*", text)


def chunk_words(text: str, chunk_size: int = 450, overlap: int = 80) -> List[str]:
    words = clean_text(text).split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words)]
    chunks = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(words), step):
        chunk = words[start : start + chunk_size]
        if len(chunk) < 60 and chunks:
            break
        chunks.append(" ".join(chunk))
    return chunks


def load_corpus(json_dir: Path = DATA_JSON_DIR) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    sections: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []
    for file in sorted(json_dir.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        paper_id = data.get("filename") or file.stem
        title = clean_text(data.get("title", ""))
        abstract = clean_text(data.get("abstract", ""))
        if abstract:
            sections.append(
                {
                    "paper_id": paper_id,
                    "title": title,
                    "section_name": "ABSTRACT",
                    "text": abstract,
                    "source_file": str(file),
                }
            )
        for section in data.get("sections", []) or []:
            text = clean_text(section.get("content", ""))
            if not text:
                continue
            item = {
                "paper_id": paper_id,
                "title": title,
                "section_name": clean_text(section.get("section_title", section.get("category", ""))) or "SECTION",
                "text": text,
                "source_file": str(file),
            }
            sections.append(item)
        for sec in sections[-(len(data.get("sections", []) or []) + (1 if abstract else 0)) :]:
            for idx, chunk in enumerate(chunk_words(sec["text"])):
                chunks.append({**sec, "chunk_id": f"{sec['paper_id']}::{sec['section_name']}::{idx}", "text": chunk})
    return sections, chunks


class BM25:
    def __init__(self, documents: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(doc) for doc in documents]
        self.doc_len = [len(doc) for doc in self.docs]
        self.avgdl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.df = Counter()
        for doc in self.docs:
            self.df.update(set(doc))
        self.n = len(self.docs)
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in self.df.items()
        }
        self.tf = [Counter(doc) for doc in self.docs]

    def score(self, query: str) -> List[float]:
        q_tokens = tokenize(query)
        scores = [0.0] * self.n
        for term in q_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * self.doc_len[i] / max(1e-9, self.avgdl))
                scores[i] += idf * (freq * (self.k1 + 1)) / denom
        return scores


def top_k(scores: List[float], k: int = 10) -> List[int]:
    return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]


def cache_load(path: Path, default: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def cache_save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def call_gemini(client, types, prompt: str, *, json_mode: bool = False, model: str = "gemini-3-flash-preview") -> str:
    config = types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=768,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            if not response.text:
                raise RuntimeError("empty Gemini response")
            return response.text.strip()
        except Exception as exc:
            last_error = exc
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"Gemini failed: {last_error}")


def translate_questions(client, types, questions: List[str]) -> Dict[str, str]:
    cache_path = OUTPUT_DIR / "question_translations.json"
    cache = cache_load(cache_path, {})
    changed = False
    for q in questions:
        key = hashlib.sha1(q.encode("utf-8")).hexdigest()
        if key in cache:
            continue
        prompt = (
            "Translate the following Vietnamese scientific question into natural English for information retrieval. "
            "Keep proper nouns, formulas, species names, metrics, and dataset names unchanged. "
            "Return only the English translation.\n\n"
            f"Question: {q}"
        )
        try:
            cache[key] = call_gemini(client, types, prompt)
        except Exception as exc:
            cache[key] = q
            cache[f"{key}:translation_error"] = str(exc)
        changed = True
        cache_save(cache_path, cache)
    if changed:
        cache_save(cache_path, cache)
    return {q: cache[hashlib.sha1(q.encode('utf-8')).hexdigest()] for q in questions}


def truncate_text(text: str, max_chars: int = 1200) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " ..."


def format_text_context(contexts: List[Dict[str, Any]], max_chars_per_context: int = 1200) -> str:
    payload = []
    for i, ctx in enumerate(contexts, 1):
        payload.append(
            {
                "rank": i,
                "paper_id": ctx.get("paper_id"),
                "paper_title": ctx.get("title"),
                "section": ctx.get("section_name"),
                "content": truncate_text(ctx.get("text", ""), max_chars_per_context),
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_answer_prompt(question: str, context_json: str) -> str:
    return f"""
Bạn là AI chuyên gia trả lời câu hỏi khoa học theo cơ chế retrieval-augmented generation.

NHIỆM VỤ: Trả lời câu hỏi dựa hoàn toàn vào ngữ cảnh được cung cấp.

NGUYÊN TẮC:
1. Chỉ dùng thông tin từ ngữ cảnh, không bịa đặt.
2. Nếu không có bằng chứng trực tiếp, trả lời đúng một câu: "Không có dữ liệu về chủ đề này trong corpus."
3. Trả lời ngắn gọn, đúng trọng tâm câu hỏi.
4. Trả lời bằng cùng ngôn ngữ với câu hỏi.
5. Cuối câu trả lời thêm mục "📌 Nguồn tham chiếu" và liệt kê paper/section chính đã dùng.

Câu hỏi: {question}

Ngữ cảnh JSON:
```json
{context_json}
```

Câu trả lời:
""".strip()


def answer_from_context(client, types, question: str, contexts: List[Dict[str, Any]]) -> Tuple[str, float]:
    prompt = build_answer_prompt(question, format_text_context(contexts))
    start = time.perf_counter()
    answer = call_gemini(client, types, prompt)
    return answer, time.perf_counter() - start


def bm25_retrieve(question: str, question_en: str, bm25: BM25, sections: List[Dict[str, Any]], k: int = 10):
    query = f"{question} {question_en}"
    start = time.perf_counter()
    scores = bm25.score(query)
    indices = top_k(scores, k)
    elapsed = time.perf_counter() - start
    return [sections[i] | {"retrieval_score": scores[i]} for i in indices], elapsed


def build_vector_index(chunks: List[Dict[str, Any]], model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name)
    cache_path = OUTPUT_DIR / f"vector_index_{safe_model}.npz"
    text_hash = hashlib.sha1(
        "\n".join(f"{c.get('chunk_id')}::{c.get('text')[:120]}" for c in chunks).encode("utf-8")
    ).hexdigest()

    model = SentenceTransformer(model_name)
    if cache_path.exists():
        data = np.load(cache_path, allow_pickle=True)
        if str(data["text_hash"]) == text_hash and int(data["count"]) == len(chunks):
            return {"model": model, "embeddings": data["embeddings"], "model_name": model_name}

    texts = [
        f"passage: Title: {c.get('title')}\nSection: {c.get('section_name')}\nContent: {c.get('text')}"
        for c in chunks
    ]
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    np.savez_compressed(cache_path, embeddings=embeddings, text_hash=text_hash, count=len(chunks))
    return {"model": model, "embeddings": embeddings, "model_name": model_name}


def vector_retrieve(vector_index: Dict[str, Any], question_en: str, chunks: List[Dict[str, Any]], k: int = 10):
    start = time.perf_counter()
    query = f"query: {question_en}"
    query_embedding = vector_index["model"].encode([query], normalize_embeddings=True)[0]
    scores = vector_index["embeddings"] @ query_embedding
    indices = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)[:k]
    elapsed = time.perf_counter() - start
    return [chunks[i] | {"retrieval_score": float(scores[i])} for i in indices], elapsed


def parse_first_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.I | re.M).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("No JSON object")
    return json.JSONDecoder().raw_decode(cleaned[start:])[0]


def parse_judge_output(text: str) -> Dict[str, Any]:
    try:
        return parse_first_json(text)
    except Exception:
        pass

    data: Dict[str, Any] = {}
    patterns = {
        "faithfulness": r"faithfulness[\"'\s:=-]+([01](?:\.\d+)?)",
        "relevancy": r"(?:relevancy|answer_relevancy)[\"'\s:=-]+([01](?:\.\d+)?)",
        "context_precision": r"context[_\s-]*precision[\"'\s:=-]+([01](?:\.\d+)?)",
        "context_recall": r"context[_\s-]*recall[\"'\s:=-]+([01](?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text or "", flags=re.I)
        if match:
            data[key] = float(match.group(1))
    for key in ("unsupported_answer", "controlled_refusal"):
        match = re.search(key + r"[\"'\s:=-]+(true|false)", text or "", flags=re.I)
        if match:
            data[key] = match.group(1).lower() == "true"
    if all(key in data for key in patterns):
        data.setdefault("unsupported_answer", False)
        data.setdefault("controlled_refusal", False)
        data.setdefault("notes", "parsed_with_regex")
        return data
    raise ValueError("Could not parse judge output")


def judge_answer(
    client,
    types,
    question: str,
    reference: str,
    answer: str,
    contexts: List[Dict[str, Any]],
    model: str = "gemini-3-flash-preview",
) -> Dict[str, Any]:
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
    try:
        return parse_judge_output(call_gemini(client, types, prompt, json_mode=True, model=model))
    except Exception as exc:
        return {
            "faithfulness": None,
            "relevancy": None,
            "context_precision": None,
            "context_recall": None,
            "unsupported_answer": None,
            "controlled_refusal": None,
            "notes": f"judge_failed: {exc}",
        }


def average(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else None


def run(args):
    client, types = load_backend_modules()
    questions = read_test_set()
    if args.limit:
        questions = questions[: args.limit]
    sections, chunks = load_corpus()
    print(f"Loaded {len(questions)} questions, {len(sections)} sections, {len(chunks)} chunks", flush=True)

    translations = translate_questions(client, types, [q["question"] for q in questions])
    bm25 = BM25([f"{s.get('title')} {s.get('section_name')} {s.get('text')}" for s in sections])

    result_path = OUTPUT_DIR / "comparison_results.jsonl"
    csv_path = OUTPUT_DIR / "comparison_results.csv"

    completed = set()
    if result_path.exists() and args.resume:
        for line in result_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if args.rerun_errors and obj.get("error"):
                continue
            completed.add((obj["method"], obj["question_id"]))

    all_methods = ["Lexical BM25 RAG", "Vector RAG", "Proposed KG-RAG"]
    methods = all_methods
    if args.methods:
        wanted = {m.strip().lower() for m in args.methods.split(",") if m.strip()}
        aliases = {
            "bm25": "Lexical BM25 RAG",
            "keyword": "Lexical BM25 RAG",
            "lexical": "Lexical BM25 RAG",
            "vector": "Vector RAG",
            "kg": "Proposed KG-RAG",
            "kgrag": "Proposed KG-RAG",
            "kg-rag": "Proposed KG-RAG",
        }
        methods = []
        for key in wanted:
            if key in aliases and aliases[key] not in methods:
                methods.append(aliases[key])
        if not methods:
            raise RuntimeError("Không nhận diện được --methods. Dùng: bm25,vector,kg")

    use_kg = "Proposed KG-RAG" in methods and not args.skip_kg
    ask_graphrag = None
    kg_url = "" if args.kg_direct else args.kg_url
    if use_kg and not kg_url:
        ask_graphrag = load_kg_rag()

    vector_index = None
    if "Vector RAG" in methods:
        started = time.perf_counter()
        print("Building/loading vector index ...", flush=True)
        vector_index = build_vector_index(chunks, args.vector_model)
        print(f"Vector index ready in {time.perf_counter() - started:.2f}s", flush=True)
    with result_path.open("a", encoding="utf-8") as out:
        for qid, item in enumerate(questions, 1):
            q = item["question"]
            ref = item["reference_answer"]
            print(console_text(f"[{qid}/{len(questions)}] {q[:80]}"), flush=True)

            for method in methods:
                if (method, qid) in completed:
                    continue
                error = None
                contexts: List[Dict[str, Any]] = []
                answer = ""
                retrieval_time = 0.0
                generation_time = 0.0
                try:
                    if method == "Lexical BM25 RAG":
                        contexts, retrieval_time = bm25_retrieve(q, translations[q], bm25, sections, args.top_k)
                        answer, generation_time = answer_from_context(client, types, q, contexts)
                    elif method == "Vector RAG":
                        contexts, retrieval_time = vector_retrieve(vector_index, translations[q], chunks, args.top_k)
                        answer, generation_time = answer_from_context(client, types, q, contexts)
                    else:
                        if not use_kg:
                            continue
                        start = time.perf_counter()
                        if kg_url:
                            answer, source_nodes, timings = ask_kg_via_http(kg_url, q)
                        else:
                            answer, source_nodes, timings = ask_graphrag(q, "all", [])
                        total = time.perf_counter() - start
                        retrieval_time = (
                            float(timings.get("retrieval_ms", 0)) + float(timings.get("ranking_ms", 0))
                        ) / 1000.0
                        generation_time = float(timings.get("llm", {}).get("answer_synthesis", 0)) / 1000.0
                        contexts = [
                            {
                                "paper_id": "Neo4j",
                                "title": name,
                                "section_name": "KG node/evidence",
                                "text": name,
                                "retrieval_score": None,
                            }
                            for name in (source_nodes or [])
                        ]
                        if not generation_time:
                            generation_time = max(0.0, total - retrieval_time)
                except Exception as exc:
                    error = str(exc)
                    answer = f"ERROR: {error}"

                judge = judge_answer(client, types, q, ref, answer, contexts) if (not args.no_judge and not error) else {}
                row = {
                    "question_id": qid,
                    "method": method,
                    "question": q,
                    "reference_answer": ref,
                    "question_en": translations[q],
                    "retrieved_context": format_text_context(contexts),
                    "generated_answer": answer,
                    "retrieval_time": retrieval_time,
                    "generation_time": generation_time,
                    "total_time": retrieval_time + generation_time,
                    "judge_model": "gemini-3-flash-preview" if not args.no_judge else None,
                    "error": error,
                    **judge,
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()

    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        rows = [r for r in rows if r["question_id"] <= args.limit]

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
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    summary = []
    for method in all_methods:
        group = [r for r in rows if r["method"] == method]
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

    summary_path = OUTPUT_DIR / "comparison_summary.json"
    cache_save(summary_path, summary)
    latex_path = OUTPUT_DIR / "comparison_table.tex"
    lines = [
        r"\begin{table}[H]",
        r"\caption{Comparison of retrieval-augmented question-answering methods.}",
        r"\label{tab:baselinecomparison}",
        r"\centering",
        r"\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lccccc@{}}",
        r"\toprule",
        r"\textbf{Method} & \textbf{Faith.} & \textbf{Relev.} & \textbf{Ctx. P} & \textbf{Ctx. R} & \textbf{Latency (s)} \\",
        r"\midrule",
    ]
    for s in summary:
        fmt = lambda x: "--" if x is None else f"{x:.3f}"
        lines.append(
            f"{s['Method']} & {fmt(s['Faithfulness'])} & {fmt(s['Relevancy'])} & "
            f"{fmt(s['Context Precision'])} & {fmt(s['Context Recall'])} & {fmt(s['Latency (s)'])} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular*}", r"\end{table}", ""])
    latex_path.write_text("\n".join(lines), encoding="utf-8")

    print(console_text(json.dumps(summary, ensure_ascii=False, indent=2)), flush=True)
    print(f"Saved: {result_path}", flush=True)
    print(f"Saved: {csv_path}", flush=True)
    print(f"Saved: {latex_path}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Chạy thử N câu đầu; 0 = chạy đủ 45 câu")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--resume", action="store_true", help="Bỏ qua kết quả đã có trong jsonl")
    parser.add_argument("--rerun-errors", action="store_true", help="Khi dùng --resume, chạy lại các dòng đã có nhưng bị error")
    parser.add_argument("--no-judge", action="store_true", help="Chỉ sinh câu trả lời/context/time, không chấm metric")
    parser.add_argument("--skip-kg", action="store_true", help="Không chạy Proposed KG-RAG")
    parser.add_argument("--methods", default="", help="Chọn method: bm25,vector,kg. Ví dụ: --methods bm25,kg")
    parser.add_argument("--kg-url", default="http://127.0.0.1:8000/api/ask", help="Endpoint KG-RAG đang chạy")
    parser.add_argument("--kg-direct", action="store_true", help="Import và gọi trực tiếp ask_graphrag thay vì HTTP")
    parser.add_argument("--vector-model", default="sentence-transformers/all-MiniLM-L6-v2")
    run(parser.parse_args())
