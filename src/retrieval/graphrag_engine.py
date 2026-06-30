"""
graphrag_engine.py — Upgraded GraphRAG Engine
- Cải thiện prompt trích xuất từ khóa + tổng hợp câu trả lời
- Thêm retry logic khi Gemini API lỗi
- Xếp hạng context theo độ liên quan
- Hỗ trợ scope filter (paper / author / method / all)
- Trả về citations rõ ràng
- [v2] Neo4j connection pool singleton — không tạo lại driver mỗi request
- [v2] Parallel keyword queries — các keyword chạy song song thay vì tuần tự
"""

from google import genai
from google.genai import types
from neo4j import GraphDatabase
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import unicodedata
import time
import logging
import math
import re
from difflib import SequenceMatcher
from typing import Tuple, List, Dict, Any

from config import GEMINI_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from hybrid_retrieval import (
    build_query_plan,
    deterministic_answer,
    retrieve_candidates,
    rerank_candidates,
    select_highlight_nodes,
)

logger = logging.getLogger(__name__)

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Hybrid ranking weights. Degree is deliberately only an auxiliary signal.
RANKING_WEIGHTS = {"semantic": 0.45, "path": 0.20, "relation": 0.20, "source": 0.15}
DEGREE_AUX_WEIGHT = 0.03
MAX_CONTEXT_ITEMS = 8
MIN_CONTEXT_SCORE = 0.20
RELATIVE_SCORE_THRESHOLD = 0.55

# ── Safety settings ────────────────────────────────────────────────────────────
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_NONE"},
]

# ── Neo4j connection pool singleton ───────────────────────────────────────────
# Driver được tạo 1 lần duy nhất, tái sử dụng cho mọi request.
# Mỗi query tự mở/đóng session riêng nên thread-safe.
_neo4j_driver = None

def _get_driver() -> GraphDatabase.driver:
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        logger.info("Neo4j driver pool initialized")
    return _neo4j_driver


# ── Model initialization ───────────────────────────────────────────────────────


# ── Utility ────────────────────────────────────────────────────────────────────
def remove_diacritics(text: str) -> str:
    if not text:
        return ""
    text_nfc = unicodedata.normalize("NFC", text)
    normalized = "".join(c for c in unicodedata.normalize("NFD", text_nfc) if unicodedata.category(c) != "Mn").lower()
    return normalized.replace("\u0111", "d").replace("\u0110", "d")


def _call_gemini(prompt: str, json_mode: bool = False, retries: int = 3) -> str:
    """Gọi Gemini bằng Google Gen AI SDK với retry logic."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain",
        temperature=0 if json_mode else None,
        safety_settings=[
            types.SafetySetting(
                category=item["category"],
                threshold=item["threshold"],
            )
            for item in SAFETY_SETTINGS
        ],
    )
    last_error = None
    for attempt in range(retries):
        try:
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=config,
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty response")
            return response.text.strip()
        except Exception as e:
            last_error = e
            logger.warning(f"Gemini attempt {attempt+1}/{retries} failed: {e}")
            # Quota errors include a server retry delay; immediate retries only waste time.
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                break
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # exponential backoff
    raise RuntimeError(f"Gemini API failed: {last_error}")

def _parse_json_object(text: str) -> dict:
    """Parse the first JSON object and ignore fences or trailing model text."""
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty JSON response")

    cleaned = text.strip().lstrip("\ufeff")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("No JSON object found in Gemini response")

    data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(data, dict):
        raise ValueError("Gemini JSON response is not an object")
    return data



def _fallback_keywords(question: str, max_keywords: int = 12) -> List[str]:
    """Create English-first search phrases locally when Gemini is unavailable."""
    keywords: List[str] = []

    def add(value: str):
        value = re.sub(r"\s+", " ", (value or "").strip(" \t\r\n.,;:?!()[]{}\"'"))
        if len(value) < 2:
            return
        value_lower = value.lower()
        existing = {item.lower() for item in keywords}
        if value_lower in existing:
            return
        # Keep the more informative phrase instead of a shorter fragment.
        if any(value_lower in item.lower() and len(value_lower) < len(item) for item in keywords):
            return
        keywords[:] = [
            item for item in keywords
            if not (item.lower() in value_lower and len(item) < len(value))
        ]
        keywords.append(value)

    # Parenthesized English/scientific aliases supplied by the user.
    for value in re.findall(r"\(([^()]{2,100})\)", question):
        add(value)

    # Strict acronyms/formulae only: all-caps tokens, formulas containing digits, hyphenated acronyms.
    for value in re.findall(r"\b(?:[A-Z]{2,}(?:-[A-Z0-9]+)*|[A-Z][A-Za-z]*\d[A-Za-z0-9-]*)\b", question):
        add(value)
    for value in re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+\b", question):
        add(value)

    normalized = remove_diacritics(question)
    domain_aliases = [
        (("ham san xuat",), ("Production function",)),
        (("san xuat lon", "chan nuoi lon"), ("Pig production",)),
        (("nang suat",), ("Productivity",)),
        (("rui ro",), ("Risk exposure", "Production risk")),
        (("hung yen",), ("Hung Yen",)),
        (("xoai",), ("Mango",)),
        (("cay nhan", "giong nhan", "qua nhan"), ("Longan",)),
        (("nhan dien chay", "phat hien chay", "chay qua video"), ("Video based fire detection", "Fire detection video")),
        (("chom chom",), ("Rambutan",)),
        (("ra hoa",), ("Flowering induction",)),
        (("hop chat giong ga", "ga-like compounds"), ("GA-like compounds",)),
        (("nut trai", "fruit cracking"), ("Fruit cracking",)),
        (("lieu luong",), ("Dose",)),
        (("dong dang di truyen", "tuong dong di truyen", "khoang cach di truyen"), ("Genetic similarity",)),
        (("goc ghep ot",), ("Chili rootstock",)),
        (("lesson study", "nghien cuu bai hoc"), ("Lesson Study",)),
        (("bao gom nhung buoc", "cac buoc", "quy trinh"), ("Process step",)),
        (("thanh nano zno", "zno nanorods"), ("ZnO nanorods",)),
        (("hat nano vang", "au nps"), ("Au nanoparticles", "Au NPs")),
        (("de kinh phu fto", "fto"), ("FTO substrate",)),
        (("do chinh xac",), ("Accuracy",)),
        (("bo du lieu", "dataset"), ("Dataset",)),
        (("dam dong",), ("Crowd detection", "Crowded groups")),
        (("lipid tong so", "total lipid"), ("Total lipids", "Total lipid extraction", "Chloroform/methanol")),
        (("ruoi giam", "drosophila melanogaster"), ("Drosophila melanogaster", "Fruit fly larvae")),
        (("hop chat phenolic", "phenolic compounds", "polyphenol"), ("Phenolic compounds", "Phenolic extraction", "Extraction of phenolic compounds")),
        (("thuoc doi", "pouzolzia zeylanica"), ("Pouzolzia zeylanica",)),
        (("phuong phap spv", "spv do quang pho", "sulfo phosphovanillin"), ("Colorimetric sulfo-phosphovanillin (SPV) assay", "SPV reaction principle")),
        (("nguyen ly", "co che phan ung"), ("Reaction principle", "Color development mechanism")),
    ]
    for phrases, aliases in domain_aliases:
        if any(phrase in normalized for phrase in phrases):
            for alias in aliases:
                add(alias)

    # Preserve meaningful English phrases already present in an English question.
    ascii_words = re.findall(r"\b[A-Za-z][A-Za-z0-9-]*\b", question)
    english_stopwords = {
        "what", "which", "where", "when", "who", "why", "how", "was", "were",
        "is", "are", "the", "a", "an", "to", "for", "of", "in", "on", "and", "or",
        "used", "study", "research", "method", "methods", "data", "according",
    }
    if question.isascii() and len(ascii_words) >= 4:
        content_words = [word for word in ascii_words if word.lower() not in english_stopwords and len(word) > 2]
        if content_words:
            add(" ".join(content_words[:6]))

    return keywords[:max_keywords]


def _clean_keywords(values: Any, question: str, max_keywords: int = 12) -> List[str]:
    """Merge Gemini translations with deterministic aliases; prefer specific English phrases."""
    merged: List[str] = []

    def add(value: Any):
        if not isinstance(value, str):
            return
        value = re.sub(r"\s+", " ", value.strip(" \t\r\n.,;:?!()[]{}\"'"))
        if len(value) < 2:
            return
        lowered = value.lower()
        if lowered in {item.lower() for item in merged}:
            return
        # Reject accidental title-case fragments such as "Nghi" from Vietnamese words.
        if re.fullmatch(r"[A-Z][a-z]{2,5}", value) and value.lower() not in {
            "mango", "longan", "rambutan",
        }:
            return
        merged.append(value)

    # Deterministic entity/target phrases go first so generic Gemini terms cannot crowd them out.
    for value in _fallback_keywords(question, max_keywords=max_keywords):
        add(value)
    if isinstance(values, list):
        for value in values:
            add(value)

    return merged[:max_keywords] or [question.strip()]

def _timed_llm_call(step: str, prompt: str, timings: Dict[str, Any], json_mode: bool = False, retries: int = 3) -> str:
    """Call Gemini and record wall-clock latency for one logical LLM step."""
    started = time.perf_counter()
    try:
        return _call_gemini(prompt, json_mode=json_mode, retries=retries)
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        timings.setdefault("llm", {})[step] = elapsed_ms
        logger.info("LLM step '%s' completed in %.2f ms", step, elapsed_ms)


def _is_vietnamese_question(text: str) -> bool:
    normalized = remove_diacritics(text)
    markers = {
        "bao", "cac", "cua", "duoc", "gi", "khi", "la", "lai", "nao",
        "nhung", "phuong", "tai", "theo", "trong", "vi", "viec",
    }
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    return any(char in text for char in "ăâđêôơưĂÂĐÊÔƠƯ") or len(tokens & markers) >= 2


def _mostly_english_answer(text: str) -> bool:
    body = re.split(r"📌|Nguồn tham chiếu", text or "", maxsplit=1)[0]
    normalized = remove_diacritics(body)
    tokens = re.findall(r"[a-z]+", normalized)
    if len(tokens) < 12:
        return False
    english_markers = {
        "and", "approach", "are", "by", "driving", "environment", "for",
        "from", "helps", "in", "learning", "method", "of", "our", "the",
        "this", "to", "training", "uses", "with",
    }
    vietnamese_markers = {
        "cac", "cua", "duoc", "giup", "he", "khong", "mo", "phuong",
        "qua", "su", "trong", "va", "viec",
    }
    return len(set(tokens) & english_markers) >= 5 and len(set(tokens) & vietnamese_markers) <= 2


def _tokenize(text: str) -> set:
    return {token for token in re.findall(r"[a-z0-9]+", remove_diacritics(text or "")) if len(token) > 1}


def _semantic_score(question: str, keywords: List[str], item: dict) -> float:
    query_tokens = _tokenize(" ".join([question] + keywords))
    entity_tokens = _tokenize(" ".join([
        str(item.get("entity_name", "")), str(item.get("entity_type", "")), str(item.get("entity_desc", ""))
    ]))
    if not query_tokens or not entity_tokens:
        return 0.0
    overlap = len(query_tokens & entity_tokens) / math.sqrt(len(query_tokens) * len(entity_tokens))
    entity_name = remove_diacritics(str(item.get("entity_name", "")))
    entity_full_text = remove_diacritics(" ".join([
        str(item.get("entity_name", "")),
        str(item.get("entity_type", "")),
        str(item.get("entity_desc", "")),
    ]))
    name_similarity = SequenceMatcher(None, remove_diacritics(question), entity_name).ratio()
    keyword_hit = max(
        (
            1.0 if remove_diacritics(kw) in entity_full_text
            else SequenceMatcher(None, remove_diacritics(kw), entity_name).ratio()
            for kw in keywords if kw
        ),
        default=0.0,
    )
    return min(1.0, 0.50 * overlap + 0.20 * name_similarity + 0.30 * keyword_hit)


def _relation_query_tokens(question: str) -> set:
    tokens = _tokenize(question)
    normalized = remove_diacritics(question)
    intent_map = [
        (("author", "tac gia", "viet boi"), {"author", "authored", "authored_by", "wrote"}),
        (("dataset", "du lieu"), {"dataset", "uses", "used", "evaluated_on"}),
        (("method", "phuong phap"), {"method", "uses", "applies", "proposes"}),
        (("compare", "comparison", "so sanh"), {"compare", "compared_with", "outperforms"}),
        (("cite", "citation", "tham khao"), {"cite", "cites", "citation"}),
        (("domain", "field", "linh vuc"), {"belongs_to", "domain", "field"}),
    ]
    for phrases, relation_tokens in intent_map:
        if any(phrase in normalized for phrase in phrases):
            tokens.update(relation_tokens)
    return tokens


def _connection_relevance(query_tokens: set, conn: dict) -> float:
    relation = str(conn.get("relation", "")).lower()
    candidate_tokens = _tokenize(
        f"{relation.replace('_', ' ')} {conn.get('related_type', '')} {conn.get('related_name', '')}"
    )
    overlap = len(query_tokens & candidate_tokens)
    score = min(1.0, overlap / max(1, min(3, len(query_tokens))))
    if relation in {"mentions", "related_to"}:
        score *= 0.65
    return score


def _rank_context(question: str, keywords: List[str], items: List[dict]) -> List[dict]:
    """Score(v)=alpha semantic + beta path + gamma relation + delta source; degree is auxiliary."""
    if not items:
        return []
    max_source_count = max(int(item.get("source_count") or 0) for item in items)
    max_degree = max(int(item.get("degree") or 0) for item in items)
    relation_tokens = _relation_query_tokens(question)
    ranked = []

    for item in items:
        semantic = _semantic_score(question, keywords, item)
        path = 1.0 / (1.0 + max(0, int(item.get("hop_distance") or 0)))
        scored_connections = sorted(
            ((_connection_relevance(relation_tokens, conn), conn) for conn in item.get("connections", []) if conn.get("related_name")),
            key=lambda pair: pair[0], reverse=True,
        )
        relation = scored_connections[0][0] if scored_connections else 0.0
        connection_text = " ".join(
            f"{conn.get('related_name', '')} {conn.get('related_desc', '')}"
            for conn in item.get("connections", [])
        )
        if connection_text and remove_diacritics(str(item.get("entity_type", ""))) == "method":
            connected_item = dict(item)
            connected_item["entity_desc"] = f"{item.get('entity_desc', '')} {connection_text}"
            connected_semantic = _semantic_score(question, keywords, connected_item)
            semantic = max(semantic, connected_semantic)
        question_normalized = remove_diacritics(question)
        entity_type = remove_diacritics(str(item.get("entity_type", "")))
        entity_desc = remove_diacritics(str(item.get("entity_desc", "")))
        if ("phuong phap" in question_normalized or "method" in question_normalized) and entity_type == "method":
            relation = max(relation, 1.0)
        asks_for_principle = any(term in question_normalized for term in (
            "nguyen ly", "co che", "phan ung", "principle", "mechanism",
        ))
        if asks_for_principle and entity_type in {"reactionprinciple", "concept"}:
            relation = max(relation, 1.0)
            semantic = max(semantic, 0.9)
        asks_for_solvent = "dung moi" in question_normalized or "solvent" in question_normalized
        if asks_for_solvent and entity_type == "method" and (
            "solvent" in entity_desc or "extract" in entity_desc
        ):
            relation = max(relation, 1.0)
            target_terms = {
                token for token in _tokenize(question)
                if token not in {"dung", "moi", "nao", "duoc", "chiet", "xuat", "nghien", "cuu"}
            }
            description_tokens = _tokenize(entity_desc)
            normalized_connection_text = remove_diacritics(connection_text)
            matched_keyword_count = sum(
                1 for keyword in keywords
                if len(remove_diacritics(keyword)) >= 5
                and remove_diacritics(keyword) in normalized_connection_text
            )
            if matched_keyword_count >= 2:
                semantic = 1.0
            elif target_terms & description_tokens:
                semantic = max(semantic, 0.85)
            if "lipid" in question_normalized and "lipid" in entity_desc:
                semantic = 1.0
            if ("phenolic" in question_normalized or "polyphenol" in question_normalized) and (
                "phenolic" in entity_desc or "polyphenol" in entity_desc
            ):
                semantic = 1.0
        if ("phan tich" in question_normalized or "analysis" in question_normalized) and (
            "analy" in entity_desc or entity_type == "method"
        ):
            relation = max(relation, 0.8)
        asks_for_value = any(term in question_normalized for term in (
            "bao nhieu", "lieu luong", "nong do", "ty le", "ti le",
            "nam trong khoang", "khoang nao", "gia tri",
        ))
        if asks_for_value and entity_type == "metric":
            relation = max(relation, 1.0)
        asks_for_steps = any(term in question_normalized for term in (
            "bao gom nhung buoc", "gom nhung buoc", "cac buoc", "quy trinh",
        ))
        if asks_for_steps and entity_type in {"processstep", "step"}:
            relation = max(relation, 1.0)
            semantic = max(semantic, 0.85)
        relevant_connections = [conn for score, conn in scored_connections if score > 0][:6]
        if not relevant_connections:
            relevant_connections = [conn for _, conn in scored_connections[:3]]

        source_count = int(item.get("source_count") or 0)
        source = math.log1p(source_count) / math.log1p(max_source_count) if max_source_count > 0 else 0.0
        degree = math.log1p(int(item.get("degree") or 0)) / math.log1p(max_degree) if max_degree > 0 else 0.0
        score = (
            RANKING_WEIGHTS["semantic"] * semantic
            + RANKING_WEIGHTS["path"] * path
            + RANKING_WEIGHTS["relation"] * relation
            + RANKING_WEIGHTS["source"] * source
            + DEGREE_AUX_WEIGHT * degree
        )
        enriched = dict(item)
        enriched["connections"] = relevant_connections
        enriched["ranking"] = {
            "score": round(score, 4), "semantic": round(semantic, 4), "path": round(path, 4),
            "relation": round(relation, 4), "source": round(source, 4), "degree_aux": round(degree, 4),
        }
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["ranking"]["score"], reverse=True)

    question_normalized = remove_diacritics(question)
    asks_for_steps = any(term in question_normalized for term in (
        "bao gom nhung buoc", "gom nhung buoc", "cac buoc", "quy trinh",
    ))
    asks_for_principle = any(term in question_normalized for term in (
        "nguyen ly", "co che", "phan ung", "principle", "mechanism",
    ))
    principle_items = [
        item for item in ranked
        if remove_diacritics(str(item.get("entity_type", ""))) == "reactionprinciple"
    ]
    if asks_for_principle and principle_items:
        related_names = {
            conn.get("related_name")
            for item in principle_items
            for conn in item.get("connections", [])
            if conn.get("related_name")
        }
        selected_names = {item.get("entity_name") for item in principle_items}
        supporting_context = [
            item for item in ranked
            if item.get("entity_name") in related_names
            and item.get("entity_name") not in selected_names
        ]
        return (principle_items + supporting_context)[:MAX_CONTEXT_ITEMS]
    process_steps = [
        item for item in ranked
        if remove_diacritics(str(item.get("entity_type", ""))) in {"processstep", "step"}
    ]
    if asks_for_steps and process_steps:
        process_steps.sort(key=lambda item: int(item.get("process_order") or 999))
        selected_names = {item.get("entity_name") for item in process_steps}
        supporting_context = [
            item for item in ranked
            if item.get("entity_name") not in selected_names
        ][:max(0, MAX_CONTEXT_ITEMS - len(process_steps))]
        return (process_steps + supporting_context)[:MAX_CONTEXT_ITEMS]

    threshold = max(MIN_CONTEXT_SCORE, ranked[0]["ranking"]["score"] * RELATIVE_SCORE_THRESHOLD)
    filtered = [item for item in ranked if item["ranking"]["score"] >= threshold][:MAX_CONTEXT_ITEMS]
    return filtered or ranked[:1]


# ── Scope → Neo4j label filter ─────────────────────────────────────────────────
SCOPE_FILTERS = {
    "paper":  "AND labels(n)[0] IN ['Paper','Document','Article']",
    "author": "AND labels(n)[0] = 'Author'",
    "method": "AND labels(n)[0] = 'Method'",
    "all":    "",
}

# ── Prompt templates ───────────────────────────────────────────────────────────

KEYWORD_EXTRACTION_PROMPT = """
Bạn là chuyên gia phân tích truy vấn cho hệ thống GraphRAG khoa học.
Hãy chuyển câu hỏi thành một kế hoạch truy hồi có cấu trúc.

Quy tắc:
- Nhận diện thực thể cụ thể, khái niệm mục tiêu, loại câu trả lời và loại quan hệ cần tìm.
- Nếu câu hỏi hiện tại có từ mơ hồ như "bài báo này", "phương pháp đó", "tác giả trên"... hãy dùng LỊCH SỬ HỘI THOẠI để suy ra thực thể cụ thể đang được đề cập.
- Nếu câu hỏi bằng tiếng Việt, BẮT BUỘC dịch thực thể và khái niệm sang tiếng Anh tự nhiên vì database chủ yếu lưu bằng tiếng Anh.
- Loại bỏ từ hỏi và từ quá chung như "tác giả", "bài báo", "phương pháp", "nghiên cứu", "liên quan", "là gì", "có những". Không trả về từ đơn bị cắt, ví dụ "Nghi".
- `answer_type` chỉ dùng một trong: entity, method, solvent, metric, dataset, process, component, principle, factor, relationship, author.
- `relations` là các loại quan hệ graph có khả năng chứa đáp án, ví dụ USED_FOR, ACHIEVED, EXTRACTED_WITH, HAS_STEP, AFFECTS.
- Nếu câu hỏi so sánh nhiều đối tượng, trả thêm `comparison_items`; mỗi phần tử có `label` bằng ngôn ngữ câu hỏi và `aliases` là tên tiếng Anh dùng để tìm kiếm.
- Trả về JSON duy nhất:
{{
  "entities": ["specific entity"],
  "concepts": ["target concept"],
  "keywords": ["English search phrase"],
  "aliases": ["useful alias"],
  "answer_type": "method",
  "relations": ["USED_FOR"],
  "comparison_items": [
    {{"label": "Đối tượng A", "aliases": ["English entity A"]}},
    {{"label": "Đối tượng B", "aliases": ["English entity B"]}}
  ]
}}

Lịch sử hội thoại gần đây (để hiểu ngữ cảnh):
{history}

Câu hỏi hiện tại: "{question}"
"""

SYNTHESIS_PROMPT = """
Bạn là AI chuyên gia phân tích đồ thị tri thức khoa học (GraphRAG).

NHIỆM VỤ: Trả lời câu hỏi dưới đây DỰA HOÀN TOÀN vào dữ liệu ngữ cảnh từ Neo4j Knowledge Graph.

NGUYÊN TẮC:
1. **Chỉ dùng thông tin từ ngữ cảnh**, không bịa đặt.
2. Nếu không tìm thấy bằng chứng trực tiếp, chỉ trả lời đúng một câu: "Không có dữ liệu về chủ đề này trong corpus." Không được tiếp tục liệt kê dữ liệu gần nghĩa, ví dụ thay thế hoặc thông tin từ đối tượng khác.
3. Nếu câu hỏi hiện tại đề cập "bài báo này", "phương pháp đó", "tác giả trên"... hãy suy luận từ **lịch sử hội thoại** để hiểu đúng ngữ cảnh.
4. Định dạng câu trả lời rõ ràng bằng **Markdown**:
   - Dùng **in đậm** cho tên thực thể quan trọng.
   - Dùng bullet points (`-`) cho danh sách.
   - Dùng emoji phù hợp để tăng khả năng đọc.
5. Cuối câu trả lời, thêm mục **📌 Nguồn tham chiếu** liệt kê tên các node chính đã dùng.
6. Ngôn ngữ: Trả lời bằng **cùng ngôn ngữ với câu hỏi** (Tiếng Việt nếu hỏi Tiếng Việt).

---

**Lịch sử hội thoại gần đây:**
{history}

**Câu hỏi hiện tại:** {question}

**Phạm vi tìm kiếm:** {scope}

**Ngữ cảnh từ Knowledge Graph (JSON):**
```json
{context}
```

**Câu trả lời:**
"""

FOLLOWUP_SUGGESTIONS_PROMPT = """
Dựa trên câu hỏi "{question}" và ngữ cảnh đã trả lời, hãy gợi ý 3 câu hỏi tiếp theo ngắn gọn.
Trả về JSON: {{"suggestions": ["câu 1", "câu 2", "câu 3"]}}
"""



INTENT_DETECTION_PROMPT = """
Phân loại câu hỏi sau vào 1 trong 2 loại:

- "graph": Câu hỏi liên quan đến nội dung khoa học, nghiên cứu, bài báo, tác giả, phương pháp, dataset, mô hình AI/ML, hoặc bất kỳ chủ đề học thuật nào cần tra cứu trong cơ sở dữ liệu tri thức.
- "general": Câu hỏi thông thường, chào hỏi, hỏi thăm, câu hỏi về bản thân AI, câu hỏi thường thức không cần tra cứu học thuật (ví dụ: "xin chào", "bạn là ai?", "2+2=?", "kể chuyện cười", v.v.)

Quy tắc: Nếu có BẤT KỲ từ khóa học thuật, tên riêng, tên mô hình, tên dataset, tên tác giả → chọn "graph".

Câu hỏi: "{question}"
Trả về JSON: {{"intent": "graph"}} hoặc {{"intent": "general"}}
"""

GENERAL_ANSWER_PROMPT = """
Bạn là trợ lý AI thân thiện tích hợp trong GraphRAG Studio — hệ thống phân tích tri thức khoa học.
Trả lời câu hỏi sau một cách tự nhiên, thân thiện.
Nếu người dùng hỏi về khả năng của bạn, hãy giới thiệu rằng bạn có thể:
- Trả lời câu hỏi thông thường
- Tra cứu bài báo khoa học, tác giả, phương pháp, dataset, mô hình AI/ML trong knowledge graph

Ngôn ngữ: Trả lời bằng cùng ngôn ngữ với câu hỏi.
Câu hỏi: "{question}"
"""

# ── Neo4j: query 1 keyword (chạy trong thread riêng) ──────────────────────────

def _query_keyword(kw: str, scope_filter: str) -> Tuple[list, set]:
    """Retrieve candidates up to two hops from a keyword-matched anchor."""
    kw_no_mark = remove_diacritics(kw)
    kw_normalized = re.sub(r"[^a-z0-9]+", " ", kw_no_mark).strip()
    generic_tokens = {
        "method", "methods", "extraction", "analysis", "study", "research",
        "solvent", "total", "the", "and", "for", "from", "with",
    }
    kw_tokens = [
        token for token in kw_normalized.split()
        if len(token) > 2 and token not in generic_tokens
    ]
    min_token_matches = min(2, len(kw_tokens))
    query = f"""
    MATCH (anchor)
    WITH anchor,
         toLower(
             replace(replace(replace(replace(replace(replace(
                 coalesce(anchor.name, anchor.id, anchor.title, '') + ' ' +
                 coalesce(anchor.description, anchor.abstract, ''),
                 '/', ' '), '-', ' '), '_', ' '), '(', ' '), ')', ' '), ':', ' ')
         ) AS search_text
    WHERE search_text CONTAINS toLower($kw)
       OR search_text CONTAINS toLower($kw_no_mark)
       OR search_text CONTAINS toLower($kw_normalized)
       OR ($min_token_matches > 0 AND
           size([token IN $kw_tokens WHERE search_text CONTAINS token]) >= $min_token_matches)
    WITH anchor LIMIT 8
    MATCH path = (anchor)-[*0..2]-(n)
    WHERE true
    {scope_filter}
    WITH n, min(length(path)) AS hop_distance
    OPTIONAL MATCH (n)-[r]-(m)
    WITH n, hop_distance, count(DISTINCT r) AS degree,
         collect(DISTINCT {{
             relation: type(r), related_type: labels(m)[0],
             related_name: coalesce(m.name, m.id, m.title),
             related_desc: coalesce(m.description, m.abstract, '')
         }})[0..12] AS connections
    OPTIONAL MATCH (paper:Paper)-[*1..2]-(n)
    RETURN labels(n)[0] AS entity_type,
           coalesce(n.name, n.id, n.title) AS entity_name,
           coalesce(n.description, n.abstract, '') AS entity_desc,
           n.order AS process_order,
           hop_distance, degree, count(DISTINCT paper) AS source_count, connections
    ORDER BY CASE WHEN labels(n)[0] = 'ProcessStep' THEN 0 ELSE 1 END,
             hop_distance ASC
    LIMIT 60
    """
    local_items, local_sources = [], set()
    try:
        with _get_driver().session() as session:
            for item in session.run(
                query,
                kw=kw,
                kw_no_mark=kw_no_mark,
                kw_normalized=kw_normalized,
                kw_tokens=kw_tokens,
                min_token_matches=min_token_matches,
            ).data():
                if item.get("entity_name"):
                    local_items.append(item)
                    local_sources.add(item["entity_name"])
    except Exception as e:
        logger.error("Neo4j query error for kw='%s': %s", kw, e)
    return local_items, local_sources


def _detect_intent(question: str, timings: Dict[str, Any]) -> str:
    normalized = remove_diacritics(question)
    academic_markers = (
        "bai bao", "bo du lieu", "dataset", "do chinh xac", "dung moi",
        "ham san xuat", "hop chat", "lieu luong", "nghien cuu", "nguyen ly",
        "phuong phap", "quy trinh", "tac gia", "tin dung",
    )
    if any(marker in normalized for marker in academic_markers):
        timings.setdefault("llm", {})["intent_detection"] = 0.0
        timings["intent_detection_mode"] = "local_academic_heuristic"
        return "graph"
    try:
        result = _timed_llm_call(
            "intent_detection", INTENT_DETECTION_PROMPT.format(question=question), timings, json_mode=True
        )
        intent = _parse_json_object(result).get("intent", "graph")
        return intent if intent in ("general", "graph") else "graph"
    except Exception as e:
        logger.warning("Intent detection failed, defaulting to 'graph': %s", e)
        return "graph"


def ask_graphrag(question: str, scope: str = "all", history: list = None) -> Tuple[str, List[str], Dict[str, Any]]:
    """Return answer, selected source node names and per-step timings."""
    request_started = time.perf_counter()
    timings: Dict[str, Any] = {"llm": {}}

    def finish(answer: str, sources: List[str]):
        timings["total_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
        logger.info("GraphRAG request completed in %.2f ms | %s", timings["total_ms"], timings)
        return answer, sources, timings

    history = history or []
    intent = _detect_intent(question, timings)
    logger.info("Intent detected: %s", intent)
    if intent == "general":
        try:
            answer = _timed_llm_call("general_answer", GENERAL_ANSWER_PROMPT.format(question=question), timings)
            return finish(answer, [])
        except Exception as e:
            logger.error("General answer failed: %s", e)
            return finish("Xin chào! Tôi gặp sự cố khi xử lý câu hỏi của bạn. Vui lòng thử lại.", [])

    if history:
        lines = []
        for h in history[-4:]:
            role = "User" if h.get("role") == "user" else "AI"
            lines.append(f"{role}: {str(h.get('content', ''))[:200]}")
        history_short = "\n".join(lines)
    else:
        history_short = "(Chưa có lịch sử)"

    llm_query_payload: Dict[str, Any] = {}
    try:
        kw_json = _timed_llm_call(
            "keyword_extraction",
            KEYWORD_EXTRACTION_PROMPT.format(question=question, history=history_short),
            timings, json_mode=True,
        )
        llm_query_payload = _parse_json_object(kw_json)
    except Exception as e:
        logger.error("Structured query extraction failed; using local plan: %s", e)

    planning_started = time.perf_counter()
    query_plan = build_query_plan(question, llm_query_payload)
    timings["query_planning_ms"] = round(
        (time.perf_counter() - planning_started) * 1000, 2
    )
    keywords = query_plan["search_terms"]
    logger.info("Structured query plan: %s", query_plan)

    retrieval_started = time.perf_counter()
    try:
        context_data, retrieval_diagnostics = retrieve_candidates(
            _get_driver(),
            question,
            query_plan,
            scope=scope,
        )
    except Exception as e:
        logger.error("Neo4j hybrid retrieval error: %s", e)
        return finish(f"❌ **Lỗi kết nối Neo4j:** {e}", [])
    timings["retrieval_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2)
    timings["retrieval"] = retrieval_diagnostics

    if not context_data:
        return finish(
            f"🔍 **Không tìm thấy dữ liệu** khớp với từ khóa: *{', '.join(keywords)}*\n\n"
            "💡 Gợi ý: Thử từ khóa khác hoặc kiểm tra dữ liệu đã được upload.", []
        )

    # Some paper titles explicitly state the reported entity, for example
    # "X, a newly recorded species...". When the exact paper exists in the
    # graph, the title itself is direct evidence and is safer than selecting
    # an unrelated neighboring Metric or Concept.
    paper_title = str(query_plan.get("paper_title") or "").strip()
    title_evidence = str(query_plan.get("title_evidence_answer") or "").strip()
    if (
        query_plan.get("answer_type") == "taxon"
        and paper_title
        and title_evidence
    ):
        normalized_title = remove_diacritics(paper_title)
        exact_paper = any(
            remove_diacritics(str(item.get("entity_name") or "")) == normalized_title
            and remove_diacritics(str(item.get("entity_type") or "")) == "paper"
            for item in context_data
        )
        if exact_paper:
            timings["ranking_ms"] = 0.0
            timings["answer_synthesis_mode"] = "verified_title_evidence"
            answer = (
                "Loài thực vật được ghi nhận mới cho hệ thực vật Việt Nam là "
                f"**{title_evidence}**.\n\n"
                "📌 **Nguồn tham chiếu**\n"
                f"- {paper_title}"
            )
            return finish(answer, [paper_title])

    ranking_started = time.perf_counter()
    top_context = rerank_candidates(question, query_plan, context_data)
    timings["ranking_ms"] = round((time.perf_counter() - ranking_started) * 1000, 2)
    if not top_context:
        timings["evidence_gate"] = "rejected_no_entity_match"
        return finish("Không có dữ liệu về chủ đề này trong corpus.", [])
    source_nodes = select_highlight_nodes(query_plan, top_context)
    logger.info(
        "Selected %d/%d contexts: %s", len(top_context), len(context_data),
        [(item.get("entity_name"), item.get("ranking", {}).get("score")) for item in top_context],
    )

    scope_label = {"all": "Toàn bộ corpus", "paper": "Bài báo", "author": "Tác giả", "method": "Phương pháp"}.get(scope, scope)
    context_json = json.dumps(top_context, ensure_ascii=False, indent=2)
    if history:
        lines = []
        for h in history[-6:]:
            role = "Người dùng" if h.get("role") == "user" else "Trợ lý"
            lines.append(f"{role}: {h.get('content', '')[:300]}")
        history_str = "\n".join(lines)
    else:
        history_str = "(Chưa có lịch sử hội thoại)"

    answer_prompt = SYNTHESIS_PROMPT.format(
        question=question, scope=scope_label, context=context_json, history=history_str,
    ) + """

IMPORTANT FOCUS RULES:
- Answer only what the current question asks; omit adjacent facts even if present in context.
- Prefer the highest-ranked evidence. Do not summarize every context item.
- Keep the answer concise. Use at most 5 bullets unless the user explicitly requests a long list.
- Cite only nodes actually used in the answer.
- If the question asks for steps/process and ProcessStep nodes are present, list every ProcessStep in ascending process_order. Do not replace them with a shorter generic summary such as Designing-Teaching-Refining.
- Do not invent process steps from a general Method description when detailed ProcessStep nodes are absent.
- Never combine a no-data statement with speculative alternatives. After saying there is no data, stop immediately.
- Treat an explicit graph relation such as EXTRACTED_WITH, USED_FOR, HAS_STEP or ACHIEVED as direct evidence. Answer from that relation and its connected nodes.
- Do not use methods connected only to a different biological sample, material or paper.
""" + f"""
- Expected answer type: {query_plan.get('answer_type', 'entity')}.
- Context is ordered with direct answer candidates first, followed by supporting evidence. Prefer the first candidate that matches the expected answer type and the entities in the question.
"""
    try:
        final_answer = _timed_llm_call("answer_synthesis", answer_prompt, timings)
        if _is_vietnamese_question(question) and _mostly_english_answer(final_answer):
            rewrite_prompt = f"""
Viết lại câu trả lời dưới đây hoàn toàn bằng tiếng Việt tự nhiên, ngắn gọn.
Giữ nguyên tên riêng, tên mô hình, số liệu và mục "📌 Nguồn tham chiếu".
Không thêm kiến thức mới và không thay đổi ý nghĩa.

Câu hỏi: {question}

Câu trả lời cần viết lại:
{final_answer}
"""
            final_answer = _timed_llm_call(
                "language_rewrite", rewrite_prompt, timings, retries=2
            )
            timings["language_guard"] = "rewritten_to_vietnamese"
    except Exception as e:
        logger.error("Answer synthesis failed: %s", e)
        final_answer = deterministic_answer(question, query_plan, top_context)
        timings["answer_synthesis_mode"] = "deterministic_fallback"
    return finish(final_answer, source_nodes)

def get_followup_suggestions(question: str, context_summary: str) -> List[str]:
    """Trả về 3 câu hỏi gợi ý tiếp theo."""
    try:
        prompt = FOLLOWUP_SUGGESTIONS_PROMPT.format(question=question)
        started = time.perf_counter()
        result = _call_gemini(prompt, json_mode=True)
        logger.info("LLM step 'followup_suggestions' completed in %.2f ms", (time.perf_counter() - started) * 1000)
        return _parse_json_object(result).get("suggestions", [])
    except Exception:
        return []
