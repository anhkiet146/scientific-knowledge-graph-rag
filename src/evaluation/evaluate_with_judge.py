"""
evaluate_prf1.py
════════════════════════════════════════════════════════════════
Đánh giá hệ thống NER + RE từ extract_entities.py theo P / R / F1.

Hai chế độ:
  1. ANNOTATION MODE  — so sánh với ground truth do người gán nhãn
  2. JUDGE MODE       — dùng Claude làm "annotator tự động" trên sample nhỏ
                        để sinh ground truth nhanh, rồi tính P/R/F1

Cấu trúc JSON (output của extract_entities.py):
  {
    "filename": "paper.json",
    "paper_title": "...",
    "extraction_result": {
      "entities":  [{"id": "...", "type": "Concept|Method|...", "description": "..."}],
      "relations": [{"source": "...", "target": "...", "type": "USED_FOR|..."}]
    }
  }

Entity types : Concept, Method, Dataset, Metric, Domain, Author, Institution
Relation types: BELONGS_TO, ACHIEVED, USED_FOR, EVALUATED_ON, AFFILIATED_WITH
════════════════════════════════════════════════════════════════
"""

import json
import time
import random
import os
from pathlib import Path
from collections import defaultdict
import anthropic

# ─── CẤU HÌNH ────────────────────────────────────────────────
EXTRACTED_FOLDER    = r'E:\LLM\data\new_extract'   # output extract_entities.py
PREPROCESSED_FOLDER = r'E:\LLM\data\json'           # output preprocess_pdf.py
ANNOTATION_FILE     = 'ground_truth.json'           # file ground truth (nếu có)
OUTPUT_FILE         = 'eval_prf1_results.json'

SAMPLE_SIZE   = 50      # số file dùng để Judge sinh ground truth (mode 2)
SLEEP_BETWEEN = 1.5     # giây, tránh rate limit Claude API

ENTITY_TYPES   = ["Concept", "Method", "Dataset", "Metric", "Domain", "Author", "Institution"]
RELATION_TYPES = ["BELONGS_TO", "ACHIEVED", "USED_FOR", "EVALUATED_ON", "AFFILIATED_WITH"]

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    raise ValueError("Please set ANTHROPIC_API_KEY before running judge evaluation.")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── PROMPT CHO JUDGE SINH GROUND TRUTH ──────────────────────
ANNOTATOR_PROMPT = """
Bạn là chuyên gia gán nhãn dữ liệu cho hệ thống trích xuất thông tin khoa học.

Dưới đây là nội dung một bài báo. Hãy trích xuất TẤT CẢ entities và relations quan trọng làm ground truth.

**Entity types được phép:**
- Concept    : khái niệm/vấn đề nghiên cứu trung tâm
- Method     : phương pháp, mô hình, thuật toán, vật liệu, thiết bị
- Dataset    : tập dữ liệu dùng để train/test/đánh giá
- Metric     : kết quả đo được (có giá trị số cụ thể)
- Domain     : lĩnh vực nghiên cứu chính
- Author     : tác giả
- Institution: tổ chức/trường đại học

**Relation types được phép:**
- BELONGS_TO    : Concept/Method thuộc về Domain
- ACHIEVED      : Method/Dataset đạt được Metric
- USED_FOR      : Method được dùng để giải quyết Concept/Dataset
- EVALUATED_ON  : Method được đánh giá trên Dataset
- AFFILIATED_WITH: Author thuộc Institution

**Văn bản bài báo:**
{paper_text}

Trả về ĐÚNG format JSON sau, không thêm text nào khác:
{{
  "entities": [
    {{"id": "tên ngắn gọn ≤8 từ", "type": "loại entity"}}
  ],
  "relations": [
    {{"source": "id entity nguồn", "target": "id entity đích", "type": "loại relation"}}
  ]
}}

Lưu ý: id trong relations phải khớp chính xác với id trong entities.
"""


# ════════════════════════════════════════════════════════════════
# PHẦN 1 — ĐỌC DỮ LIỆU
# ════════════════════════════════════════════════════════════════

def load_extracted(json_file: Path) -> dict:
    """Đọc output của extract_entities.py"""
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
    result = data.get("extraction_result", {})
    if not isinstance(result, dict):
        return {"entities": [], "relations": []}
    entities  = result.get("entities", []) or []
    relations = result.get("relations", []) or []
    return {
        "entities":  [e for e in entities  if isinstance(e, dict)],
        "relations": [r for r in relations if isinstance(r, dict)],
    }


def load_paper_text(filename: str, preprocessed_folder: str) -> str:
    """Ghép text gốc từ preprocess_pdf.py để gửi cho Judge"""
    source_file = Path(preprocessed_folder) / filename
    if not source_file.exists():
        return ""
    with open(source_file, encoding="utf-8") as f:
        src = json.load(f)

    parts = []
    title = src.get("title", "").strip()
    raw_h = src.get("raw_header", "").strip()
    abstract = src.get("abstract", "").strip()

    if title:    parts.append(f"TITLE: {title}")
    if raw_h:    parts.append(f"HEADER:\n{raw_h}")
    if abstract: parts.append(f"ABSTRACT:\n{abstract}")

    for sec in src.get("sections", []):
        if isinstance(sec, dict):
            content = sec.get("content", "").strip()
            stitle  = sec.get("section_title", "")
            if content:
                parts.append(f"[{stitle}]\n{content}")

    return "\n\n".join(parts)[:5000]


# ════════════════════════════════════════════════════════════════
# PHẦN 2 — JUDGE SINH GROUND TRUTH
# ════════════════════════════════════════════════════════════════

def judge_annotate(paper_text: str) -> dict:
    """Dùng Claude sinh ground truth cho 1 bài báo"""
    prompt = ANNOTATOR_PROMPT.format(paper_text=paper_text)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(clean)
        entities  = [e for e in data.get("entities",  []) if isinstance(e, dict)]
        relations = [r for r in data.get("relations", []) if isinstance(r, dict)]
        return {"entities": entities, "relations": relations}
    except json.JSONDecodeError:
        return {"entities": [], "relations": []}


def build_ground_truth_with_judge(
    extracted_folder: str,
    preprocessed_folder: str,
    sample_size: int,
) -> dict:
    """
    Sample ngẫu nhiên sample_size files, gọi Claude sinh ground truth,
    trả về dict {filename: {"entities": [...], "relations": [...]}}
    """
    all_files = sorted(Path(extracted_folder).glob("*.json"))
    random.seed(42)
    sampled = random.sample(all_files, min(sample_size, len(all_files)))

    print(f"\n🤖 Judge đang sinh ground truth cho {len(sampled)} files...\n")
    ground_truth = {}

    for i, json_file in enumerate(sampled, 1):
        paper_text = load_paper_text(json_file.name, preprocessed_folder)
        if not paper_text:
            print(f"  [{i:>3}] ⚠ Bỏ qua {json_file.name} — không có text gốc")
            continue

        try:
            gt = judge_annotate(paper_text)
            ground_truth[json_file.name] = gt
            print(f"  [{i:>3}] ✅ {json_file.name:<45} "
                  f"ent={len(gt['entities'])} rel={len(gt['relations'])}")
        except Exception as e:
            print(f"  [{i:>3}] ❌ {json_file.name}: {e}")

        time.sleep(SLEEP_BETWEEN)

    return ground_truth


# ════════════════════════════════════════════════════════════════
# PHẦN 3 — CHUẨN HÓA & SO KHỚP
# ════════════════════════════════════════════════════════════════

def normalize_entity_id(eid: str) -> str:
    """Chuẩn hóa tên entity để so khớp mềm (bỏ hoa/thường, khoảng trắng thừa)"""
    return " ".join(eid.lower().strip().split())


def entity_to_key(ent: dict, soft: bool = False) -> tuple:
    """
    Tạo key để so khớp entity.
    - strict : (normalized_id, type)   — cả tên lẫn type phải khớp
    - soft   : (normalized_id,)        — chỉ khớp tên, bỏ qua type
    """
    eid  = normalize_entity_id(str(ent.get("id", "")))
    etype = str(ent.get("type", "")).strip()
    return (eid,) if soft else (eid, etype)


def relation_to_key(rel: dict, soft: bool = False) -> tuple:
    """
    Tạo key để so khớp relation.
    - strict : (norm_src, norm_tgt, type)
    - soft   : (norm_src, norm_tgt)     — bỏ qua loại relation
    """
    src  = normalize_entity_id(str(rel.get("source", "")))
    tgt  = normalize_entity_id(str(rel.get("target", "")))
    rtype = str(rel.get("type", "")).strip().upper()
    return (src, tgt) if soft else (src, tgt, rtype)


# ════════════════════════════════════════════════════════════════
# PHẦN 4 — TÍNH P / R / F1
# ════════════════════════════════════════════════════════════════

def prf1(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    return {
        "precision": round(precision, 4),
        "recall":    round(recall,    4),
        "f1":        round(f1,        4),
        "tp": tp, "fp": fp, "fn": fn,
    }


def evaluate_one(pred: dict, gold: dict, soft: bool = False) -> dict:
    """
    So sánh prediction vs ground truth cho 1 file.
    Trả về dict chứa P/R/F1 cho NER (tổng + per type) và RE (tổng + per type).
    """
    # ── NER ──────────────────────────────────────────────────────
    pred_ents = {entity_to_key(e, soft) for e in pred.get("entities", [])}
    gold_ents = {entity_to_key(e, soft) for e in gold.get("entities", [])}

    ner_tp = len(pred_ents & gold_ents)
    ner_fp = len(pred_ents - gold_ents)
    ner_fn = len(gold_ents - pred_ents)
    ner_overall = prf1(ner_tp, ner_fp, ner_fn)

    # Per entity type
    ner_per_type = {}
    for etype in ENTITY_TYPES:
        if soft:
            p_set = {k for k in pred_ents}
            g_set = {k for k in gold_ents}
        else:
            p_set = {k for k in pred_ents if k[1] == etype}
            g_set = {k for k in gold_ents if k[1] == etype}
        tp = len(p_set & g_set)
        fp = len(p_set - g_set)
        fn = len(g_set - p_set)
        if tp + fp + fn > 0:
            ner_per_type[etype] = prf1(tp, fp, fn)

    # ── RE ───────────────────────────────────────────────────────
    pred_rels = {relation_to_key(r, soft) for r in pred.get("relations", [])}
    gold_rels = {relation_to_key(r, soft) for r in gold.get("relations", [])}

    re_tp = len(pred_rels & gold_rels)
    re_fp = len(pred_rels - gold_rels)
    re_fn = len(gold_rels - pred_rels)
    re_overall = prf1(re_tp, re_fp, re_fn)

    # Per relation type
    re_per_type = {}
    for rtype in RELATION_TYPES:
        if soft:
            p_set = {k for k in pred_rels}
            g_set = {k for k in gold_rels}
        else:
            p_set = {k for k in pred_rels if k[2] == rtype}
            g_set = {k for k in gold_rels if k[2] == rtype}
        tp = len(p_set & g_set)
        fp = len(p_set - g_set)
        fn = len(g_set - p_set)
        if tp + fp + fn > 0:
            re_per_type[rtype] = prf1(tp, fp, fn)

    return {
        "ner": {"overall": ner_overall, "per_type": ner_per_type},
        "re":  {"overall": re_overall,  "per_type": re_per_type},
    }


def aggregate_results(per_file: list) -> dict:
    """
    Macro-average P/R/F1 qua tất cả files.
    Cũng tính micro (tổng TP/FP/FN trước khi chia).
    """
    def macro(key1, key2):
        scores = [r[key1][key2] for r in per_file
                  if key1 in r and key2 in r[key1]]
        if not scores:
            return {}
        return {
            "macro_precision": round(sum(s["precision"] for s in scores) / len(scores), 4),
            "macro_recall":    round(sum(s["recall"]    for s in scores) / len(scores), 4),
            "macro_f1":        round(sum(s["f1"]        for s in scores) / len(scores), 4),
            "micro": prf1(
                sum(s["tp"] for s in scores),
                sum(s["fp"] for s in scores),
                sum(s["fn"] for s in scores),
            ),
        }

    def macro_per_type(task, types):
        result = {}
        for t in types:
            scores = [r[task]["per_type"][t] for r in per_file
                      if task in r and t in r[task].get("per_type", {})]
            if not scores:
                continue
            result[t] = {
                "macro_f1":        round(sum(s["f1"]        for s in scores) / len(scores), 4),
                "macro_precision": round(sum(s["precision"] for s in scores) / len(scores), 4),
                "macro_recall":    round(sum(s["recall"]    for s in scores) / len(scores), 4),
                "support": sum(s["tp"] + s["fn"] for s in scores),
            }
        return result

    return {
        "ner": {
            "overall":  macro("ner", "overall"),
            "per_type": macro_per_type("ner", ENTITY_TYPES),
        },
        "re": {
            "overall":  macro("re", "overall"),
            "per_type": macro_per_type("re", RELATION_TYPES),
        },
    }


# ════════════════════════════════════════════════════════════════
# PHẦN 5 — IN KẾT QUẢ
# ════════════════════════════════════════════════════════════════

def print_results(agg: dict, n_files: int):
    sep = "─" * 55

    print(f"\n{'═'*55}")
    print(f"  KẾT QUẢ ĐÁNH GIÁ P / R / F1  ({n_files} files)")
    print(f"{'═'*55}")

    for task, label in [("ner", "NER (Entity Recognition)"),
                         ("re",  "RE  (Relation Extraction)")]:
        ov = agg[task]["overall"]
        print(f"\n▌ {label}")
        print(sep)
        if ov:
            print(f"  {'':20s}  {'Precision':>9}  {'Recall':>9}  {'F1':>9}")
            print(f"  {'Macro avg':20s}  {ov['macro_precision']:>9.4f}  "
                  f"{ov['macro_recall']:>9.4f}  {ov['macro_f1']:>9.4f}")
            mi = ov["micro"]
            print(f"  {'Micro avg':20s}  {mi['precision']:>9.4f}  "
                  f"{mi['recall']:>9.4f}  {mi['f1']:>9.4f}")
        else:
            print("  (không có dữ liệu)")

        pt = agg[task]["per_type"]
        if pt:
            print(f"\n  Chi tiết theo loại:")
            print(f"  {'Type':25s}  {'Precision':>9}  {'Recall':>9}  {'F1':>9}  {'Support':>7}")
            print(f"  {'─'*25}  {'─'*9}  {'─'*9}  {'─'*9}  {'─'*7}")
            for t, s in sorted(pt.items(), key=lambda x: -x[1]["macro_f1"]):
                print(f"  {t:25s}  {s['macro_precision']:>9.4f}  "
                      f"{s['macro_recall']:>9.4f}  {s['macro_f1']:>9.4f}  "
                      f"{s['support']:>7}")

    print(f"\n{'═'*55}\n")


# ════════════════════════════════════════════════════════════════
# PHẦN 6 — MAIN
# ════════════════════════════════════════════════════════════════

def run_with_annotation(annotation_file: str, extracted_folder: str):
    """
    Chế độ 1: Dùng ground truth do người gán nhãn.
    Format annotation_file:
    {
      "paper_xyz.json": {
        "entities":  [{"id": "...", "type": "..."}],
        "relations": [{"source": "...", "target": "...", "type": "..."}]
      },
      ...
    }
    """
    print(f"\n📂 Chế độ ANNOTATION — đọc ground truth từ {annotation_file}")
    with open(annotation_file, encoding="utf-8") as f:
        ground_truth = json.load(f)

    per_file = []
    for filename, gold in ground_truth.items():
        pred_file = Path(extracted_folder) / filename
        if not pred_file.exists():
            continue
        pred = load_extracted(pred_file)
        result = evaluate_one(pred, gold, soft=False)
        result["filename"] = filename
        per_file.append(result)

    return per_file


def run_with_judge(extracted_folder: str, preprocessed_folder: str, sample_size: int):
    """
    Chế độ 2: Dùng Claude sinh ground truth tự động trên sample.
    """
    print(f"\n🤖 Chế độ JUDGE — sinh ground truth tự động ({sample_size} files)")
    ground_truth = build_ground_truth_with_judge(
        extracted_folder, preprocessed_folder, sample_size
    )

    # Lưu ground truth để dùng lại sau (tránh gọi API nhiều lần)
    with open("judge_ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)
    print(f"💾 Ground truth đã lưu tại: judge_ground_truth.json")

    per_file = []
    for filename, gold in ground_truth.items():
        pred_file = Path(extracted_folder) / filename
        if not pred_file.exists():
            continue
        pred = load_extracted(pred_file)
        result = evaluate_one(pred, gold, soft=False)
        result["filename"] = filename
        per_file.append(result)

    return per_file


def main():
    annotation_path = Path(ANNOTATION_FILE)

    if annotation_path.exists():
        per_file = run_with_annotation(ANNOTATION_FILE, EXTRACTED_FOLDER)
    else:
        print(f"ℹ️  Không tìm thấy {ANNOTATION_FILE} → chuyển sang chế độ JUDGE")
        per_file = run_with_judge(EXTRACTED_FOLDER, PREPROCESSED_FOLDER, SAMPLE_SIZE)

    if not per_file:
        print("❌ Không có kết quả nào để tính.")
        return

    agg = aggregate_results(per_file)
    print_results(agg, len(per_file))

    # Lưu kết quả đầy đủ
    output = {
        "summary": agg,
        "n_files": len(per_file),
        "per_file": per_file,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"💾 Kết quả chi tiết lưu tại: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
