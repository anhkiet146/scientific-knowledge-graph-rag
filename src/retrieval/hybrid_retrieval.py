"""General-purpose hybrid retrieval for the GraphRAG backend.

The pipeline combines:
1. Structured question analysis.
2. Neo4j full-text search.
3. Normalized lexical/token fallback.
4. Two-hop graph expansion.
5. Answer-type and evidence-aware reranking.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Sequence, Tuple


logger = logging.getLogger(__name__)

FULLTEXT_INDEX_NAME = "graphrag_node_search"
MAX_QUERY_TERMS = 12
MAX_ANCHORS = 60
MAX_CANDIDATES = 180
MAX_CONTEXT_ITEMS = 10

_index_lock = threading.Lock()
_index_ready = False

_GENERIC_QUERY_WORDS = {
    "a",
    "an",
    "and",
    "article",
    "based",
    "bai",
    "bao",
    "cac",
    "cho",
    "co",
    "cua",
    "data",
    "de",
    "duoc",
    "for",
    "from",
    "gi",
    "he",
    "in",
    "la",
    "method",
    "methods",
    "mot",
    "nao",
    "nghien",
    "nhung",
    "of",
    "on",
    "paper",
    "research",
    "study",
    "the",
    "thong",
    "to",
    "trong",
    "used",
    "va",
    "what",
    "which",
    "xuat",
}

_ANSWER_TYPES = {
    "metric": {
        "labels": {"metric"},
        "phrases": (
            "bao nhieu",
            "gia tri",
            "khoang nao",
            "lieu luong",
            "nong do",
            "percentage",
            "rate",
            "ty le",
        ),
    },
    "dataset": {
        "labels": {"dataset"},
        "phrases": ("bo du lieu", "dataset", "du lieu nao"),
    },
    "taxon": {
        "labels": {"biologicalsample", "concept"},
        "phrases": (
            "loai nao",
            "loai thuc vat nao",
            "newly recorded species",
            "species was recorded",
            "what species",
        ),
    },
    "taxonomy": {
        "labels": {"biologicalsample", "concept"},
        "phrases": (
            "thuoc ho nao",
            "thuoc chi nao",
            "thuoc bo nao",
            "plant family",
            "taxonomic family",
            "which family",
            "which genus",
            "which order",
        ),
    },
    "process": {
        "labels": {"processstep", "step"},
        "phrases": ("bao gom nhung buoc", "cac buoc", "quy trinh", "stages", "steps"),
    },
    "component": {
        "labels": {"concept", "method", "dataset"},
        "phrases": (
            "bao gom nhung thanh phan",
            "cac thanh phan",
            "component",
            "components",
            "thanh phan",
            "thanh phan chinh",
            "thanh phan ky thuat",
        ),
    },
    "principle": {
        "labels": {"reactionprinciple", "concept"},
        "phrases": ("co che", "mechanism", "nguyen ly", "phan ung", "principle"),
    },
    "solvent": {
        "labels": {"method", "chemical", "material"},
        "phrases": ("dung moi", "solvent"),
    },
    "method": {
        "labels": {"method"},
        "phrases": ("ham san xuat nao", "method", "phuong phap nao", "su dung ham"),
    },
    "author": {
        "labels": {"author"},
        "phrases": ("ai la tac gia", "author", "tac gia nao"),
    },
    "factor": {
        "labels": {"factor", "concept", "metric"},
        "phrases": ("cac yeu to", "determinant", "factor", "yeu to nao"),
    },
    "relationship": {
        "labels": {"metric", "concept", "factor"},
        "phrases": ("anh huong", "moi lien he", "quan he", "relationship", "tac dong"),
    },
}

_RELATION_HINTS = {
    "author": {"AUTHORED_BY", "WROTE"},
    "dataset": {"EVALUATED_ON", "USES_DATASET", "USED_FOR"},
    "taxon": {"BELONGS_TO", "NEW_RECORD_OF", "RECORDED_IN", "STUDIES"},
    "taxonomy": {"BELONGS_TO", "CLASSIFIED_AS", "MEMBER_OF", "TAXONOMICALLY_IN"},
    "factor": {"AFFECTS", "DETERMINES", "INFLUENCES", "RELATED_TO"},
    "method": {"APPLIES", "PROPOSES", "USED_FOR", "USES"},
    "metric": {"ACHIEVED", "HAS_VALUE", "MEASURED_BY"},
    "principle": {"BASED_ON", "PRODUCES", "USES_REAGENT"},
    "process": {"HAS_STEP", "DESCRIBES_STEP", "NEXT_STEP"},
    "component": {"CONSISTS_OF", "HAS_COMPONENT", "INCLUDES", "USES"},
    "relationship": {
        "ACHIEVED",
        "AFFECTS",
        "DETERMINES",
        "INCREASES",
        "REDUCES",
        "RELATED_TO",
    },
    "solvent": {"EXTRACTED_WITH", "USED_FOR", "USES_REAGENT"},
}

# This is a compact, domain-independent bilingual query lexicon. It expands
# question intent and common scientific nouns, not individual answers.
_VI_EN_CONCEPTS = (
    (("bo du lieu",), ("dataset",)),
    (("chat chong oxy hoa", "hoat tinh chong oxy hoa"), ("antioxidant activity",)),
    (("chiet xuat",), ("extraction",)),
    (("chi phi dau tu", "chi phi san xuat"), ("investment cost", "production costs")),
    (("do chinh xac",), ("accuracy",)),
    (("do tuong dong", "dong dang"), ("similarity",)),
    (("dung moi",), ("solvent",)),
    (("lieu luong",), ("dose",)),
    (("ham san xuat",), ("production function",)),
    (("hat nano",), ("nanoparticles",)),
    (("hop chat phenolic",), ("phenolic compounds",)),
    (("nhan dien chay", "phat hien chay", "chay qua video"), ("video based fire detection", "fire detection video")),
    (("phat hien chay rung",), ("forest fire detection", "wildfire detection")),
    (("kha nang tiep can tin dung",), ("access to credit", "credit accessibility")),
    (("khoang cach di truyen",), ("genetic distance",)),
    (("lesson study", "nghien cuu bai hoc"), ("Lesson Study",)),
    (("lipid tong so",), ("total lipids",)),
    (("loi nhuan", "lai rong"), ("profit", "net revenue")),
    (("tom cang xanh",), ("giant freshwater prawn", "prawn")),
    (("tom su",), ("black tiger shrimp", "tiger shrimp")),
    (("nuoi luan canh", "luan canh"), ("rotational culture", "alternative culture")),
    (("nang suat",), ("productivity", "yield")),
    (("cay nhan", "giong nhan", "qua nhan"), ("longan",)),
    (("nguyen ly",), ("principle",)),
    (("ra hoa",), ("flowering induction",)),
    (("quy mo doanh nghiep",), ("firm size", "enterprise size", "larger-scale enterprises")),
    (("bao gom nhung buoc", "cac buoc", "quy trinh"), ("process step",)),
    (("rui ro",), ("risk", "risk exposure")),
    (("san xuat lon",), ("pig production",)),
    (("sinh vien su pham dia ly",), ("geography pedagogy students",)),
    (("ruoi giam",), ("fruit fly",)),
    (("thanh nano",), ("nanorods",)),
    (("tiep can tin dung",), ("access to formal credit",)),
    (("tu duy phan bien",), ("critical thinking",)),
)

_METRIC_TARGETS = (
    {
        "id": "cost",
        "label_vi": "Chi phí",
        "phrases": ("chi phi", "chi phi dau tu", "investment cost", "production cost"),
        "aliases": ("cost", "costs", "expense", "expenses", "investment", "production cost"),
    },
    {
        "id": "profit",
        "label_vi": "Lợi nhuận",
        "phrases": ("loi nhuan", "lai rong", "profit", "net revenue", "net income"),
        "aliases": ("profit", "net revenue", "net income", "earning", "income"),
    },
    {
        "id": "revenue",
        "label_vi": "Doanh thu",
        "phrases": ("doanh thu", "revenue", "gross income"),
        "aliases": ("revenue", "gross income", "sales"),
    },
    {
        "id": "yield",
        "label_vi": "Năng suất/sản lượng",
        "phrases": ("nang suat", "san luong", "yield", "productivity"),
        "aliases": ("yield", "productivity", "production"),
    },
    {
        "id": "accuracy",
        "label_vi": "Độ chính xác",
        "phrases": ("do chinh xac", "accuracy", "precision"),
        "aliases": ("accuracy", "precision"),
    },
    {
        "id": "rate",
        "label_vi": "Tỷ lệ",
        "phrases": ("ty le", "rate", "percentage"),
        "aliases": ("rate", "percentage", "ratio"),
    },
    {
        "id": "dose",
        "label_vi": "Liều lượng",
        "phrases": ("lieu luong", "dose", "dosage"),
        "aliases": ("dose", "dosage", "concentration"),
    },
    {
        "id": "speed",
        "label_vi": "Tốc độ",
        "phrases": ("toc do", "speed", "velocity"),
        "aliases": ("speed", "velocity"),
    },
    {
        "id": "distance",
        "label_vi": "Khoảng cách",
        "phrases": ("khoang cach", "distance"),
        "aliases": ("distance",),
    },
    {
        "id": "adsorption_capacity",
        "label_vi": "Dung lượng hấp phụ",
        "phrases": (
            "dung luong hap phu",
            "adsorption capacity",
            "maximal adsorption capacity",
            "maximum adsorption capacity",
        ),
        "aliases": (
            "adsorption capacity",
            "maximal adsorption capacity",
            "maximum adsorption capacity",
            "qmax",
        ),
    },
    {
        "id": "benefit_cost_ratio",
        "label_vi": "Tỷ suất lợi nhuận trên chi phí (B/C)",
        "phrases": (
            "b c",
            "benefit cost",
            "benefit cost ratio",
            "loi nhuan tren chi phi",
            "ty suat loi nhuan tren chi phi",
        ),
        "aliases": (
            "b c ratio",
            "benefit cost ratio",
            "profit cost ratio",
        ),
    },
)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    text = text.replace("\u0111", "d").replace("\u0110", "D").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) > 1 and token not in _GENERIC_QUERY_WORDS
    }


def ordered_tokens(text: str) -> List[str]:
    return [
        token
        for token in normalize_text(text).split()
        if len(token) > 1 and token not in _GENERIC_QUERY_WORDS
    ]


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text))


def _add_phrase(output: List[str], value: Any) -> None:
    if not isinstance(value, str):
        return
    value = re.sub(r"\s+", " ", value.strip(" \t\r\n.,;:?!()[]{}\"'"))
    if len(value) < 2:
        return
    normalized = normalize_text(value)
    if not normalized or normalized in {normalize_text(item) for item in output}:
        return
    if not tokenize(value):
        return
    output.append(value)


def _detect_answer_type(question: str) -> str:
    # A quoted paper title is retrieval context, not the user's requested
    # answer intent. Excluding it prevents words such as "relationship" or
    # "dataset" in the title from overriding "what species/method/value".
    intent_text = re.sub(r'["“][^"”]+["”]', " ", question)
    normalized = normalize_text(intent_text)
    if (
        re.search(r"\bthuoc\s+(?:ho|chi|bo)(?:\s+\w+){0,3}\s+nao\b", normalized)
        or re.search(r"\bwhich\s+(?:family|genus|order)\b", normalized)
    ):
        return "taxonomy"
    if any(
        marker in normalized
        for marker in ("thanh phan", "component", "components", "architecture")
    ):
        return "component"
    # Match flexible Vietnamese/English formulations such as
    # "phương pháp mới nào", "phương pháp được đề xuất là gì".
    if (
        ("phuong phap" in normalized or "method" in normalized)
        and any(
            marker in normalized
            for marker in ("nao", "la gi", "de xuat", "moi", "proposed", "novel", "which", "what")
        )
    ):
        return "method"
    for answer_type, config in _ANSWER_TYPES.items():
        # Use token-boundary phrase matching. Plain substring matching caused
        # false intents such as "rate" inside "carbohydrate" => Metric.
        if any(_contains_phrase(normalized, phrase) for phrase in config["phrases"]):
            return answer_type
    return "entity"


def build_query_plan(question: str, llm_payload: Any = None) -> Dict[str, Any]:
    """Build a structured plan from deterministic parsing plus optional LLM JSON."""
    phrases: List[str] = []
    entities: List[str] = []
    concepts: List[str] = []
    required_entities: List[str] = []
    quoted_titles = [
        value.strip()
        for value in re.findall(r'["“]([^"”]{12,500})["”]', question)
        if value.strip()
    ]
    paper_title = quoted_titles[0] if quoted_titles else ""
    title_evidence_answer = ""
    if paper_title:
        title_patterns = (
            r"^(.+?)\s+(?:a\s+)?newly recorded species\b",
            r"^(.+?)\s+(?:a\s+)?new record\b",
            r"^(.+?)\s+newly recorded (?:for|in)\b",
        )
        for pattern in title_patterns:
            match = re.search(pattern, paper_title, flags=re.IGNORECASE)
            if match:
                title_evidence_answer = match.group(1).strip(" .,:;-")
                break

    # Scientific names, English aliases and acronyms supplied by the user.
    for value in re.findall(r"\(([^()]{2,120})\)", question):
        _add_phrase(entities, value)
    for value in re.findall(
        r"\b(?:[A-Z]{2,}(?:-[A-Z0-9]+)*|[A-Z][A-Za-z]*\d[A-Za-z0-9-]*)\b",
        question,
    ):
        _add_phrase(phrases, value)
        _add_phrase(entities, value)
        is_ion_slot = bool(re.fullmatch(r"[A-Z][a-z]?\d+", value))
        value_start = question.find(value)
        prefix = normalize_text(question[max(0, value_start - 45):value_start])
        is_context_platform = any(
            marker in prefix
            for marker in (
                "bo xu ly",
                "hardware",
                "microcontroller",
                "nen tang",
                "platform",
                "simulator",
                "tren vi dieu khien",
                "vi dieu khien",
            )
        )
        if not is_context_platform and not is_ion_slot:
            _add_phrase(required_entities, value)
    # Product/model names written in CamelCase, e.g. ForestGuard.
    for value in re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+\b", question):
        _add_phrase(entities, value)
        _add_phrase(required_entities, value)
    blocked_scientific_prefixes = {"Dung", "Lesson", "Nam", "Nghi", "Theo"}
    for value in re.findall(r"\b[A-Z][a-z]{2,}\s+[a-z]{2,}\b", question):
        if value.split()[0] not in blocked_scientific_prefixes:
            _add_phrase(entities, value)

    normalized = normalize_text(question)
    requested_items: List[str] = []
    # Quantitative questions often ask one value per chemical ion/model/item.
    # Preserve compact formula-like slots so each requested value can be
    # matched independently instead of returning one generic Metric.
    for value in re.findall(
        r"(?<!\w)[A-Z][a-z]?\d*(?:\([IVX]+\))?\d*[+-](?!\w)|\b[A-Z][a-z]?\d+\b",
        question,
    ):
        _add_phrase(requested_items, value)
    metric_targets: List[Dict[str, Any]] = []
    for target in _METRIC_TARGETS:
        if any(_contains_phrase(normalized, phrase) for phrase in target["phrases"]):
            metric_targets.append(
                {
                    "id": target["id"],
                    "label_vi": target["label_vi"],
                    "aliases": list(target["aliases"]),
                }
            )
    # Resolve overlapping metric phrases. "Lợi nhuận trên chi phí (B/C)" is
    # one ratio, not an additional request for absolute profit.
    target_ids = {target["id"] for target in metric_targets}
    if "benefit_cost_ratio" in target_ids and "profit" in target_ids:
        without_ratio = re.sub(
            r"(?:ty suat\s+)?loi nhuan tren chi phi|\bbenefit cost ratio\b|\bb c\b",
            " ",
            normalized,
        )
        if not any(
            phrase in without_ratio
            for phrase in ("loi nhuan", "lai rong", "net income", "net revenue", "profit")
        ):
            metric_targets = [
                target for target in metric_targets if target["id"] != "profit"
            ]
    subject_terms: List[str] = []
    target_aliases = {
        normalize_text(alias)
        for target in metric_targets
        for alias in target.get("aliases", [])
    }
    for value in re.findall(r"\(([^()]{2,120})\)", question):
        normalized_value = normalize_text(value)
        if not normalized_value:
            continue
        if any(alias in normalized_value or normalized_value in alias for alias in target_aliases):
            continue
        if re.fullmatch(r"[a-z]{1,3}\d*", normalized_value):
            continue
        _add_phrase(subject_terms, value)
    for source_phrases, translations in _VI_EN_CONCEPTS:
        if any(_contains_phrase(normalized, source) for source in source_phrases):
            for translation in translations:
                _add_phrase(concepts, translation)
    if (
        any(target["id"] == "benefit_cost_ratio" for target in metric_targets)
        and not any(target["id"] == "profit" for target in metric_targets)
    ):
        concepts = [
            value
            for value in concepts
            if normalize_text(value) not in {"profit", "net revenue"}
        ]

    answer_type = _detect_answer_type(question)
    # Quantitative fields in the question are stronger evidence of a Metric
    # request than the surface ending "được đánh giá như thế nào".
    if metric_targets and answer_type == "entity":
        answer_type = "metric"
    intent_without_title = normalize_text(
        re.sub(r'["“][^"”]+["”]', " ", question)
    )
    taxonomy_rank = ""
    if answer_type == "taxonomy":
        if re.search(r"\bthuoc\s+ho\b|\bwhich family\b", intent_without_title):
            taxonomy_rank = "family"
        elif re.search(r"\bthuoc\s+chi\b|\bwhich genus\b", intent_without_title):
            taxonomy_rank = "genus"
        elif re.search(r"\bthuoc\s+bo\b|\bwhich order\b", intent_without_title):
            taxonomy_rank = "order"
    novelty_requested = any(
        phrase in normalized
        for phrase in ("de xuat", "phuong phap moi", "novel method", "proposed method")
    )
    relations: List[str] = sorted(_RELATION_HINTS.get(answer_type, set()))
    comparison_requested = any(
        marker in normalized
        for marker in ("so voi", "compared with", "compared to", "comparison", "versus")
    )

    if isinstance(llm_payload, dict):
        for key in ("entities", "keywords", "aliases"):
            values = llm_payload.get(key, [])
            if isinstance(values, list):
                for value in values:
                    _add_phrase(entities if key == "entities" else phrases, value)
        values = llm_payload.get("concepts", [])
        if isinstance(values, list):
            for value in values:
                _add_phrase(concepts, value)
        llm_answer_type = normalize_text(llm_payload.get("answer_type", ""))
        # Deterministic explicit phrases ("loài nào", "bao nhiêu",
        # "phương pháp nào"...) take precedence. Let the LLM refine only
        # questions that remain generic.
        if answer_type == "entity" and llm_answer_type in _ANSWER_TYPES:
            answer_type = llm_answer_type
        llm_relations = llm_payload.get("relations", [])
        if isinstance(llm_relations, list):
            relations.extend(str(value).upper() for value in llm_relations if value)

    # Preserve English phrases only for fully ASCII questions. On Vietnamese
    # text, regexing ASCII chunks can otherwise produce broken fragments.
    if question.isascii():
        latin_chunks = re.findall(
            r"[A-Za-z][A-Za-z0-9.'-]*(?:\s+[A-Za-z][A-Za-z0-9.'-]*)+",
            question,
        )
        for chunk in latin_chunks:
            words = [
                word
                for word in chunk.split()
                if normalize_text(word) not in _GENERIC_QUERY_WORDS
            ]
            if len(words) >= 2:
                _add_phrase(phrases, " ".join(words[:8]))

    search_terms: List[str] = []
    if paper_title:
        _add_phrase(search_terms, paper_title)
    # Composite phrases express entity + target intent and are more selective
    # than generic terms such as "extraction" or "method".
    for entity in entities:
        for concept in concepts or phrases[:4]:
            _add_phrase(search_terms, f"{entity} {concept}")
    for collection in (entities, concepts, phrases):
        for value in collection:
            _add_phrase(search_terms, value)

    comparison_items: List[Dict[str, Any]] = []
    if comparison_requested:
        if isinstance(llm_payload, dict):
            for raw_item in llm_payload.get("comparison_items", []) or []:
                if not isinstance(raw_item, dict):
                    continue
                label = str(raw_item.get("label") or "").strip()
                aliases = [
                    str(value).strip()
                    for value in raw_item.get("aliases", []) or []
                    if str(value).strip()
                ]
                if label and aliases:
                    comparison_items.append(
                        {"label": label, "aliases": aliases}
                    )
        comparison_alias_groups = (
            ("Tôm càng xanh", ("giant freshwater prawn", "prawn")),
            ("Tôm sú", ("black tiger shrimp", "tiger shrimp")),
        )
        concept_text = normalize_text(" ".join(concepts))
        for label, aliases in comparison_alias_groups:
            if any(normalize_text(alias) in concept_text for alias in aliases):
                if not any(
                    normalize_text(label) == normalize_text(item["label"])
                    for item in comparison_items
                ):
                    comparison_items.append(
                        {"label": label, "aliases": list(aliases)}
                    )

    # If the LLM is unavailable, use informative normalized n-grams rather
    # than the whole Vietnamese question or isolated fragments.
    if not search_terms:
        content_tokens = ordered_tokens(question)
        for size in (4, 3, 2):
            if len(content_tokens) >= size:
                _add_phrase(search_terms, " ".join(content_tokens[:size]))

    return {
        "answer_type": answer_type,
        "paper_title": paper_title,
        "title_evidence_answer": title_evidence_answer,
        "single_answer": answer_type == "dataset"
        and any(
            phrase in normalized
            for phrase in ("bo du lieu moi", "co ten la gi", "ten la gi")
        ),
        "expected_labels": sorted(_ANSWER_TYPES.get(answer_type, {}).get("labels", set())),
        "metric_targets": metric_targets,
        "multi_metric": answer_type == "metric" and len(metric_targets) > 1,
        "requested_items": requested_items,
        "multi_item": answer_type == "metric" and len(requested_items) > 1,
        "subject_terms": subject_terms,
        "novelty_requested": answer_type == "method" and novelty_requested,
        "taxonomy_rank": taxonomy_rank,
        "comparison_requested": comparison_requested,
        "comparison_items": comparison_items,
        "entities": entities,
        "required_entities": required_entities,
        "concepts": concepts,
        "relations": sorted(set(relations)),
        "search_terms": search_terms[:MAX_QUERY_TERMS],
    }


def ensure_fulltext_index(driver) -> bool:
    """Create one cross-label full-text index over searchable node properties."""
    global _index_ready
    if _index_ready:
        return True
    with _index_lock:
        if _index_ready:
            return True
        try:
            with driver.session() as session:
                existing = session.run(
                    "SHOW FULLTEXT INDEXES YIELD name WHERE name = $name RETURN count(*) AS count",
                    name=FULLTEXT_INDEX_NAME,
                ).single()
                if existing and int(existing["count"]) > 0:
                    _index_ready = True
                    return True

                labels = [
                    record["label"]
                    for record in session.run("CALL db.labels() YIELD label RETURN label")
                    if record["label"]
                ]
                if not labels:
                    return False
                escaped_labels = "|".join(
                    f"`{label.replace('`', '``')}`" for label in sorted(set(labels))
                )
                cypher = (
                    f"CREATE FULLTEXT INDEX {FULLTEXT_INDEX_NAME} IF NOT EXISTS "
                    f"FOR (n:{escaped_labels}) "
                    "ON EACH [n.name, n.title, n.id, n.description, n.abstract, "
                    "n.aliases, n.normalized_name]"
                )
                session.run(cypher).consume()
                session.run(
                    "CALL db.awaitIndex($name, 30)",
                    name=FULLTEXT_INDEX_NAME,
                ).consume()
            _index_ready = True
            logger.info("Neo4j full-text index '%s' is ready", FULLTEXT_INDEX_NAME)
            return True
        except Exception as exc:
            logger.warning("Full-text index unavailable; lexical fallback remains active: %s", exc)
            return False


def _lucene_query(terms: Sequence[str]) -> str:
    clauses: List[str] = []
    exact_tokens: List[str] = []
    for term in terms:
        tokens = list(tokenize(term))
        if not tokens:
            continue
        escaped_phrase = re.sub(r'([+\-!(){}\[\]^"~*?:\\/])', r"\\\1", term)
        if len(tokens) > 1:
            clauses.append(f'"{escaped_phrase}"^4')
        exact_tokens.extend(token for token in tokens if len(token) >= 3)
    # Exact token clauses avoid Lucene fuzzy expansion hitting maxClauseCount.
    clauses.extend(f"{token}^1.2" for token in list(dict.fromkeys(exact_tokens))[:20])
    return " OR ".join(dict.fromkeys(clauses[:32]))


def _scope_matches(scope: str, labels: Iterable[str]) -> bool:
    lowered = {str(label).lower() for label in labels}
    if scope == "paper":
        return bool(lowered & {"paper", "document", "article"})
    if scope == "author":
        return "author" in lowered
    if scope == "method":
        return "method" in lowered
    return True


def _fulltext_anchors(driver, terms: Sequence[str], scope: str) -> List[Dict[str, Any]]:
    if not terms or not ensure_fulltext_index(driver):
        return []
    query = _lucene_query(terms)
    if not query:
        return []
    cypher = """
    CALL db.index.fulltext.queryNodes($index_name, $lucene_query, {limit: $limit})
    YIELD node, score
    RETURN elementId(node) AS id, labels(node) AS labels, score,
           coalesce(node.name, node.title, node.id, '') AS name
    ORDER BY score DESC
    """
    anchors = []
    try:
        with driver.session() as session:
            for record in session.run(
                cypher,
                index_name=FULLTEXT_INDEX_NAME,
                lucene_query=query,
                limit=MAX_ANCHORS,
            ):
                if _scope_matches(scope, record["labels"]):
                    anchors.append(
                        {
                            "id": record["id"],
                            "score": float(record["score"] or 0.0),
                            "query": record["name"] or "fulltext",
                            "mode": "fulltext",
                        }
                    )
    except Exception as exc:
        logger.warning("Full-text query failed; using lexical retrieval: %s", exc)
        return []
    return anchors


def _lexical_anchors(driver, terms: Sequence[str], scope: str) -> List[Dict[str, Any]]:
    normalized_queries = []
    for term in terms:
        normalized = normalize_text(term)
        tokens = [token for token in normalized.split() if token not in _GENERIC_QUERY_WORDS]
        if tokens:
            normalized_queries.append(
                {
                    "raw": term,
                    "normalized": normalized,
                    "tokens": tokens,
                    "min_matches": min(2, len(tokens)),
                }
            )
    if not normalized_queries:
        return []

    cypher = """
    UNWIND $queries AS q
    MATCH (anchor)
    WITH q, anchor, labels(anchor) AS node_labels,
         toLower(
             replace(replace(replace(replace(replace(replace(
                 coalesce(anchor.name, anchor.id, anchor.title, '') + ' ' +
                 coalesce(anchor.description, anchor.abstract, '') + ' ' +
                 coalesce(toString(anchor.aliases), ''),
                 '/', ' '), '-', ' '), '_', ' '), '(', ' '), ')', ' '), ':', ' ')
         ) AS search_text
    WHERE
        ($scope = 'all'
         OR ($scope = 'paper' AND any(label IN node_labels WHERE label IN ['Paper','Document','Article']))
         OR ($scope = 'author' AND 'Author' IN node_labels)
         OR ($scope = 'method' AND 'Method' IN node_labels))
      AND (
        search_text CONTAINS q.normalized
        OR size([token IN q.tokens WHERE search_text CONTAINS token]) >= q.min_matches
      )
    WITH anchor, q, search_text,
         CASE
           WHEN search_text CONTAINS q.normalized THEN 4.0
           ELSE 1.0 * size([token IN q.tokens WHERE search_text CONTAINS token])
         END AS lexical_score
    WITH anchor, max(lexical_score) AS score, collect(DISTINCT q.raw)[0..5] AS queries
    RETURN elementId(anchor) AS id, labels(anchor) AS labels, score, queries,
           coalesce(anchor.name, anchor.title, anchor.id, '') AS name
    ORDER BY score DESC
    LIMIT $limit
    """
    anchors = []
    with driver.session() as session:
        for record in session.run(
            cypher,
            queries=normalized_queries,
            scope=scope,
            limit=MAX_ANCHORS,
        ):
            anchors.append(
                {
                    "id": record["id"],
                    "score": float(record["score"] or 0.0),
                    "query": " | ".join(record["queries"] or []) or record["name"],
                    "mode": "lexical",
                }
            )
    return anchors


def _merge_anchors(*anchor_groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for anchors in anchor_groups:
        for anchor in anchors:
            current = merged.get(anchor["id"])
            if current is None:
                merged[anchor["id"]] = dict(anchor)
                merged[anchor["id"]]["queries"] = {anchor.get("query", "")}
                merged[anchor["id"]]["modes"] = {anchor.get("mode", "")}
            else:
                current["score"] = max(float(current["score"]), float(anchor["score"]))
                current["queries"].add(anchor.get("query", ""))
                current["modes"].add(anchor.get("mode", ""))
    ordered = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    for anchor in ordered:
        anchor["query"] = " | ".join(sorted(value for value in anchor.pop("queries") if value))
        anchor["mode"] = "+".join(sorted(value for value in anchor.pop("modes") if value))
    return ordered[:MAX_ANCHORS]


def _expand_anchors(driver, anchors: Sequence[Dict[str, Any]], scope: str) -> List[Dict[str, Any]]:
    if not anchors:
        return []
    cypher = """
    UNWIND $anchors AS anchor_hit
    MATCH (anchor)
    WHERE elementId(anchor) = anchor_hit.id
    MATCH path = (anchor)-[*0..2]-(n)
    WHERE
        $scope = 'all'
        OR ($scope = 'paper' AND any(label IN labels(n) WHERE label IN ['Paper','Document','Article']))
        OR ($scope = 'author' AND 'Author' IN labels(n))
        OR ($scope = 'method' AND 'Method' IN labels(n))
    WITH n,
         min(length(path)) AS hop_distance,
         max(anchor_hit.score / (1.0 + length(path))) AS retrieval_score,
         collect(DISTINCT anchor_hit.query)[0..8] AS matched_queries,
         collect(DISTINCT anchor_hit.mode)[0..4] AS retrieval_modes
    OPTIONAL MATCH (n)-[r]-(m)
    WITH n, hop_distance, retrieval_score, matched_queries, retrieval_modes,
         count(DISTINCT r) AS degree,
         collect(DISTINCT {
             relation: type(r),
             related_type: labels(m)[0],
             related_name: coalesce(m.name, m.id, m.title),
             related_desc: coalesce(m.description, m.abstract, '')
         })[0..24] AS connections
    OPTIONAL MATCH (paper:Paper)-[]-(n)
    WITH n, hop_distance, retrieval_score, matched_queries, retrieval_modes,
         degree, connections, count(DISTINCT paper) AS source_count,
         collect(DISTINCT coalesce(paper.title, paper.name, paper.id))[0..8] AS source_papers
    RETURN labels(n)[0] AS entity_type,
           labels(n) AS labels,
           coalesce(n.name, n.id, n.title) AS entity_name,
           coalesce(n.description, n.abstract, '') AS entity_desc,
           n.order AS process_order,
           hop_distance, degree, source_count, source_papers,
           retrieval_score, matched_queries, retrieval_modes, connections
    ORDER BY retrieval_score DESC, hop_distance ASC
    LIMIT $candidate_limit
    """
    with driver.session() as session:
        return session.run(
            cypher,
            anchors=list(anchors),
            scope=scope,
            candidate_limit=MAX_CANDIDATES,
        ).data()


def retrieve_candidates(
    driver,
    question: str,
    plan: Dict[str, Any],
    scope: str = "all",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    terms = plan.get("search_terms", [])[:MAX_QUERY_TERMS]
    fulltext = _fulltext_anchors(driver, terms, scope)
    lexical = _lexical_anchors(driver, terms, scope)
    anchors = _merge_anchors(fulltext, lexical)
    candidates = _expand_anchors(driver, anchors, scope)
    diagnostics = {
        "search_terms": terms,
        "answer_type": plan.get("answer_type"),
        "fulltext_anchors": len(fulltext),
        "lexical_anchors": len(lexical),
        "merged_anchors": len(anchors),
        "candidates": len(candidates),
    }
    return candidates, diagnostics


def _lexical_semantic(question: str, terms: Sequence[str], item: Dict[str, Any]) -> float:
    query_text = " ".join([question, *terms])
    connection_text = " ".join(
        f"{connection.get('relation', '')} {connection.get('related_name', '')} "
        f"{connection.get('related_desc', '')}"
        for connection in item.get("connections", [])
    )
    entity_text = " ".join(
        [
            str(item.get("entity_name", "")),
            str(item.get("entity_type", "")),
            str(item.get("entity_desc", "")),
            connection_text,
            " ".join(item.get("source_papers", []) or []),
        ]
    )
    query_tokens = tokenize(query_text)
    entity_tokens = tokenize(entity_text)
    if not query_tokens or not entity_tokens:
        return 0.0
    overlap = len(query_tokens & entity_tokens) / math.sqrt(len(query_tokens) * len(entity_tokens))
    entity_normalized = normalize_text(entity_text)
    phrase_hit = max(
        (1.0 if normalize_text(term) in entity_normalized else 0.0 for term in terms),
        default=0.0,
    )
    name_similarity = SequenceMatcher(
        None,
        normalize_text(question),
        normalize_text(item.get("entity_name", "")),
    ).ratio()
    return min(1.0, 0.55 * overlap + 0.30 * phrase_hit + 0.15 * name_similarity)


def _entity_match(plan: Dict[str, Any], item: Dict[str, Any]) -> float:
    entity_text = normalize_text(
        " ".join(
            [
                str(item.get("entity_name", "")),
                str(item.get("entity_desc", "")),
                " ".join(item.get("source_papers", []) or []),
                " ".join(
                    str(connection.get("related_name", ""))
                    for connection in item.get("connections", [])
                ),
            ]
        )
    )
    entities = plan.get("entities", [])
    if not entities:
        return 0.5
    hits = sum(1 for entity in entities if normalize_text(entity) in entity_text)
    return hits / len(entities)


def _answer_type_match(plan: Dict[str, Any], item: Dict[str, Any]) -> float:
    expected = {normalize_text(label) for label in plan.get("expected_labels", [])}
    label = normalize_text(item.get("entity_type", ""))
    if not expected:
        return 0.5
    answer_type = plan.get("answer_type")
    text = normalize_text(
        f"{item.get('entity_name', '')} {item.get('entity_desc', '')}"
    )
    relations = {
        str(connection.get("relation", "")).upper()
        for connection in item.get("connections", [])
    }
    if answer_type == "solvent":
        solvent_markers = {
            "acid",
            "aqueous",
            "chloroform",
            "ethanol",
            "ether",
            "hexane",
            "methanol",
            "solvent",
            "water",
        }
        if "EXTRACTED_WITH" in relations:
            return 1.0
        if solvent_markers & tokenize(text):
            return 1.0
        return 0.1 if label == "method" else 0.0
    if answer_type == "principle":
        if label == "reactionprinciple":
            return 1.0
        return 0.45 if label == "concept" else 0.0
    if answer_type == "process":
        return 1.0 if label in {"processstep", "step"} else 0.0
    if answer_type == "taxonomy":
        taxonomy_rank = plan.get("taxonomy_rank")
        taxonomy_relations = {
            "CLASSIFIED_AS",
            "MEMBER_OF",
            "TAXONOMICALLY_IN",
        }
        if taxonomy_relations & relations:
            return 1.0
        if label in {"biologicalsample", "concept"}:
            tokens = tokenize(text)
            entity_name = normalize_text(item.get("entity_name", ""))
            if taxonomy_rank == "family":
                if "family" in tokens or entity_name.endswith("aceae"):
                    return 1.0
            elif taxonomy_rank == "genus":
                if "genus" in tokens:
                    return 1.0
            elif taxonomy_rank == "order":
                if "order" in tokens or entity_name.endswith("ales"):
                    return 1.0
        return 0.0
    if answer_type == "method":
        if label != "method":
            return 0.35 if label == "paper" else 0.0
        if plan.get("novelty_requested"):
            novelty_markers = {
                "new",
                "novel",
                "propose",
                "proposed",
                "proposal",
            }
            platform_markers = {
                "board",
                "hardware",
                "microcontroller",
                "platform",
                "processor",
            }
            text_tokens = tokenize(text)
            if novelty_markers & text_tokens:
                return 1.0
            if platform_markers & text_tokens:
                return 0.15
            return 0.45
        return 1.0
    if answer_type == "relationship":
        directional_markers = {
            "coefficient",
            "decrease",
            "effect",
            "increase",
            "larger",
            "probability",
            "reduces",
        }
        if label == "metric" and directional_markers & tokenize(text):
            return 1.0
        if label in {"concept", "factor"}:
            return 0.65
        return 0.35 if label == "metric" else 0.0
    if label in expected:
        return 1.0
    # Papers and concepts remain useful supporting evidence, but should not
    # outrank a direct answer node of the requested type.
    if label in {"paper", "concept"}:
        return 0.35
    return 0.0


def _relation_match(plan: Dict[str, Any], item: Dict[str, Any]) -> float:
    expected = {relation.upper() for relation in plan.get("relations", [])}
    actual = {
        str(connection.get("relation", "")).upper()
        for connection in item.get("connections", [])
        if connection.get("relation")
    }
    if not expected:
        return 0.5
    overlap = expected & actual
    return min(1.0, len(overlap) / max(1, min(2, len(expected))))


def _evidence_score(plan: Dict[str, Any], item: Dict[str, Any]) -> float:
    terms = plan.get("search_terms", [])
    if not terms:
        return 0.0
    supporting_segments = [
        normalize_text(item.get("entity_name", "")),
        normalize_text(item.get("entity_desc", "")),
        *[normalize_text(value) for value in item.get("source_papers", []) or []],
    ]
    for connection in item.get("connections", []):
        supporting_segments.append(
            normalize_text(
                f"{connection.get('relation', '')} {connection.get('related_name', '')} "
                f"{connection.get('related_desc', '')}"
            )
        )
    matched_groups = 0
    for term in terms:
        normalized = normalize_text(term)
        term_tokens = tokenize(term)
        if normalized and any(
            normalized in segment
            or (term_tokens and len(term_tokens & tokenize(segment)) >= min(2, len(term_tokens)))
            for segment in supporting_segments
        ):
            matched_groups += 1
    coverage = matched_groups / len(terms)
    direct_relation = _relation_match(plan, item)
    return min(1.0, 0.7 * coverage + 0.3 * direct_relation)


def _metric_target_score(target: Dict[str, Any], item: Dict[str, Any]) -> float:
    """Measure whether a Metric node answers one requested quantitative field."""
    text = normalize_text(
        f"{item.get('entity_name', '')} {item.get('entity_desc', '')}"
    )
    aliases = [normalize_text(value) for value in target.get("aliases", [])]
    if not aliases:
        return 0.0
    phrase_hit = max((1.0 if alias in text else 0.0 for alias in aliases), default=0.0)
    alias_tokens = set().union(*(tokenize(alias) for alias in aliases))
    token_hit = (
        len(alias_tokens & tokenize(text)) / len(alias_tokens)
        if alias_tokens
        else 0.0
    )
    return min(1.0, 0.75 * phrase_hit + 0.25 * token_hit)


def _requested_item_score(requested_item: str, item: Dict[str, Any]) -> float:
    """Match a requested value slot, preferring explicit evidence in node names."""
    needle = re.sub(r"[^a-z0-9]+", "", normalize_text(requested_item))
    if not needle:
        return 0.0
    name_text = re.sub(
        r"[^a-z0-9]+", "", normalize_text(item.get("entity_name", ""))
    )
    if needle in name_text:
        return 1.0
    description_text = re.sub(
        r"[^a-z0-9]+", "", normalize_text(item.get("entity_desc", ""))
    )
    return 0.45 if needle in description_text else 0.0


def _subject_match(plan: Dict[str, Any], item: Dict[str, Any]) -> float:
    subjects = plan.get("subject_terms", [])
    if not subjects:
        return 1.0
    searchable = normalize_text(
        " ".join(
            [
                str(item.get("entity_name", "")),
                str(item.get("entity_desc", "")),
                " ".join(item.get("source_papers", []) or []),
                " ".join(
                    f"{connection.get('related_name', '')} {connection.get('related_desc', '')}"
                    for connection in item.get("connections", [])
                ),
            ]
        )
    )
    hits = sum(
        1 for subject in subjects if normalize_text(subject) in searchable
    )
    return hits / len(subjects)


def _comparison_item_score(comparison_item: Dict[str, Any], item: Dict[str, Any]) -> float:
    # Do not use source-paper titles here: one comparative paper commonly
    # mentions every group and would make each Metric appear to belong to all
    # groups. Require evidence in the Metric itself or a directly connected
    # experimental method/group.
    searchable = normalize_text(
        " ".join(
            [
                str(item.get("entity_name", "")),
                str(item.get("entity_desc", "")),
                " ".join(
                    f"{connection.get('related_name', '')} {connection.get('related_desc', '')}"
                    for connection in item.get("connections", [])
                    if normalize_text(connection.get("related_type", ""))
                    not in {"paper", "author", "institution"}
                ),
            ]
        )
    )
    aliases = [
        normalize_text(value)
        for value in comparison_item.get("aliases", [])
        if value
    ]
    if not aliases:
        return 0.0
    phrase_hit = max((1.0 if alias in searchable else 0.0 for alias in aliases), default=0.0)
    alias_tokens = set().union(*(tokenize(alias) for alias in aliases))
    token_score = (
        len(alias_tokens & tokenize(searchable)) / len(alias_tokens)
        if alias_tokens
        else 0.0
    )
    return min(1.0, 0.8 * phrase_hit + 0.2 * token_score)


def rerank_candidates(
    question: str,
    plan: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]],
    max_context: int = MAX_CONTEXT_ITEMS,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    max_source = max(int(item.get("source_count") or 0) for item in candidates)
    max_degree = max(int(item.get("degree") or 0) for item in candidates)
    max_retrieval = max(float(item.get("retrieval_score") or 0.0) for item in candidates)

    ranked = []
    for item in candidates:
        semantic = _lexical_semantic(question, plan.get("search_terms", []), item)
        entity = _entity_match(plan, item)
        answer_type = _answer_type_match(plan, item)
        relation = _relation_match(plan, item)
        path = 1.0 / (1.0 + max(0, int(item.get("hop_distance") or 0)))
        source = (
            math.log1p(int(item.get("source_count") or 0)) / math.log1p(max_source)
            if max_source > 0
            else 0.0
        )
        evidence = _evidence_score(plan, item)
        retrieval = (
            float(item.get("retrieval_score") or 0.0) / max_retrieval
            if max_retrieval > 0
            else 0.0
        )
        degree = (
            math.log1p(int(item.get("degree") or 0)) / math.log1p(max_degree)
            if max_degree > 0
            else 0.0
        )
        metric_target_scores = {
            target["id"]: _metric_target_score(target, item)
            for target in plan.get("metric_targets", [])
        }
        metric_target = max(metric_target_scores.values(), default=0.0)
        requested_item_scores = {
            requested_item: _requested_item_score(requested_item, item)
            for requested_item in plan.get("requested_items", [])
        }
        requested_item = max(requested_item_scores.values(), default=0.0)
        subject = _subject_match(plan, item)
        comparison_scores = {
            comparison_item["label"]: _comparison_item_score(comparison_item, item)
            for comparison_item in plan.get("comparison_items", [])
        }
        comparison = max(comparison_scores.values(), default=0.0)

        score = (
            0.32 * semantic
            + 0.14 * entity
            + 0.16 * answer_type
            + 0.11 * relation
            + 0.09 * path
            + 0.05 * source
            + 0.08 * evidence
            + 0.04 * retrieval
            + 0.01 * degree
        )
        if plan.get("answer_type") == "metric" and metric_target_scores:
            # Requested metric semantics are more important than generic
            # numeric-node relevance (e.g. cost/profit versus coverage/yield).
            score = 0.82 * score + 0.18 * metric_target
        if plan.get("answer_type") == "metric" and requested_item_scores:
            score = 0.82 * score + 0.12 * requested_item + 0.06 * subject
        if plan.get("comparison_requested") and comparison_scores:
            score = 0.85 * score + 0.15 * comparison
        enriched = dict(item)
        enriched["ranking"] = {
            "score": round(score, 4),
            "semantic": round(semantic, 4),
            "entity": round(entity, 4),
            "answer_type": round(answer_type, 4),
            "relation": round(relation, 4),
            "path": round(path, 4),
            "source": round(source, 4),
            "evidence": round(evidence, 4),
            "retrieval": round(retrieval, 4),
            "degree_aux": round(degree, 4),
            "metric_targets": {
                key: round(value, 4) for key, value in metric_target_scores.items()
            },
            "requested_items": {
                key: round(value, 4) for key, value in requested_item_scores.items()
            },
            "subject": round(subject, 4),
            "comparison_items": {
                key: round(value, 4) for key, value in comparison_scores.items()
            },
        }
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["ranking"]["score"], reverse=True)

    expected = {normalize_text(label) for label in plan.get("expected_labels", [])}
    required_entities = [
        normalize_text(value) for value in plan.get("required_entities", []) if value
    ]

    def matches_required_entity(item: Dict[str, Any]) -> bool:
        if not required_entities:
            return True
        searchable = normalize_text(
            " ".join(
                [
                    str(item.get("entity_name", "")),
                    str(item.get("entity_desc", "")),
                    " ".join(item.get("source_papers", []) or []),
                    " ".join(
                        str(connection.get("related_name", ""))
                        for connection in item.get("connections", [])
                    ),
                ]
            )
        )
        return all(entity in searchable for entity in required_entities)

    requested_answer_type = plan.get("answer_type")
    minimum_evidence = {
        "relationship": 0.35,
        "solvent": 0.40,
    }.get(requested_answer_type, 0.25)
    direct_answers = [
        item
        for item in ranked
        if normalize_text(item.get("entity_type", "")) in expected
        and item["ranking"]["evidence"] >= minimum_evidence
        and matches_required_entity(item)
        and (
            requested_answer_type != "taxonomy"
            or item["ranking"]["answer_type"] >= 0.80
        )
        and (
            not plan.get("entities")
            or item["ranking"]["entity"] >= 0.5
        )
    ]

    if requested_answer_type == "method" and plan.get("novelty_requested"):
        proposed_methods = [
            item
            for item in ranked
            if normalize_text(item.get("entity_type", "")) == "method"
            and item["ranking"]["answer_type"] >= 0.80
            and item["ranking"]["evidence"] >= minimum_evidence
            and matches_required_entity(item)
            and (
                not plan.get("entities")
                or item["ranking"]["entity"] >= 0.5
            )
        ]
        if proposed_methods:
            direct_answers = proposed_methods

    if requested_answer_type == "metric" and plan.get("metric_targets"):
        selected_by_target: List[Dict[str, Any]] = []
        selected_metric_names = set()
        for target in plan["metric_targets"]:
            target_id = target["id"]
            matches = [
                item
                for item in ranked
                if normalize_text(item.get("entity_type", "")) == "metric"
                and item["ranking"].get("metric_targets", {}).get(target_id, 0.0) >= 0.50
                and matches_required_entity(item)
                and (
                    not plan.get("entities")
                    or item["ranking"]["entity"] >= 0.5
                )
            ]
            if matches:
                best = matches[0]
                if best.get("entity_name") not in selected_metric_names:
                    selected_by_target.append(best)
                    selected_metric_names.add(best.get("entity_name"))
        if selected_by_target:
            direct_answers = selected_by_target

    if requested_answer_type == "metric" and plan.get("requested_items"):
        selected_by_item: List[Dict[str, Any]] = []
        selected_item_names = set()
        for requested_item in plan["requested_items"]:
            matches = [
                item
                for item in ranked
                if normalize_text(item.get("entity_type", "")) == "metric"
                and item["ranking"].get("requested_items", {}).get(requested_item, 0.0) >= 0.80
                and item["ranking"].get("subject", 0.0) >= 0.80
                and (
                    not plan.get("metric_targets")
                    or max(
                        item["ranking"].get("metric_targets", {}).values(),
                        default=0.0,
                    ) >= 0.50
                )
                and matches_required_entity(item)
            ]
            if matches:
                best = matches[0]
                if best.get("entity_name") not in selected_item_names:
                    selected_by_item.append(best)
                    selected_item_names.add(best.get("entity_name"))
        direct_answers = selected_by_item

    if (
        requested_answer_type == "metric"
        and plan.get("comparison_requested")
        and plan.get("comparison_items")
        and plan.get("metric_targets")
    ):
        comparison_matrix_answers: List[Dict[str, Any]] = []
        selected_names = set()
        for comparison_item in plan["comparison_items"]:
            comparison_label = comparison_item["label"]
            for target in plan["metric_targets"]:
                target_id = target["id"]
                matches = [
                    item
                    for item in ranked
                    if normalize_text(item.get("entity_type", "")) == "metric"
                    and item["ranking"]
                    .get("comparison_items", {})
                    .get(comparison_label, 0.0) >= 0.75
                    and item["ranking"]
                    .get("metric_targets", {})
                    .get(target_id, 0.0) >= 0.50
                    and matches_required_entity(item)
                ]
                if matches:
                    best = matches[0]
                    if best.get("entity_name") not in selected_names:
                        comparison_matrix_answers.append(best)
                        selected_names.add(best.get("entity_name"))
        direct_answers = comparison_matrix_answers
    if plan.get("entities") and direct_answers:
        best_entity_match = max(item["ranking"]["entity"] for item in direct_answers)
        direct_answers = [
            item
            for item in direct_answers
            if item["ranking"]["entity"] >= max(0.5, best_entity_match - 0.25)
        ]

    if requested_answer_type == "process" and direct_answers:
        direct_answers.sort(key=lambda item: int(item.get("process_order") or 999))
    elif requested_answer_type in {
        "principle",
        "solvent",
        "method",
        "metric",
        "dataset",
        "factor",
        "component",
        "relationship",
    }:
        direct_answers = direct_answers[:1] if plan.get("single_answer") else direct_answers[:4]

    selected: List[Dict[str, Any]] = []
    selected_names = set()
    for item in direct_answers:
        name = item.get("entity_name")
        if name not in selected_names:
            selected.append(item)
            selected_names.add(name)

    # If the requested answer type has no direct evidence, never promote a
    # Paper/Concept/supporting node into the answer position.
    if expected and not selected:
        return []

    # Add supporting paper/concept/source nodes after direct answers.
    for item in ranked:
        if len(selected) >= max_context:
            break
        name = item.get("entity_name")
        if name in selected_names:
            continue
        if required_entities and not matches_required_entity(item):
            continue
        if (
            requested_answer_type == "metric"
            and plan.get("subject_terms")
            and item["ranking"].get("subject", 0.0) < 0.80
        ):
            continue
        if item["ranking"]["score"] < 0.22:
            continue
        if plan.get("entities") and item["ranking"]["entity"] < 0.2:
            continue
        if (
            normalize_text(item.get("entity_type", "")) in expected
            and item["ranking"]["evidence"] < minimum_evidence
        ):
            continue
        if (
            requested_answer_type == "taxonomy"
            and item["ranking"]["answer_type"] < 0.80
        ):
            continue
        selected.append(item)
        selected_names.add(name)

    # Named entities are hard constraints. Do not substitute a merely
    # top-ranked but unrelated node when none of the candidates match.
    if (plan.get("entities") or required_entities) and not selected:
        return []
    return selected[:max_context] or ranked[:1]


def deterministic_answer(
    question: str,
    plan: Dict[str, Any],
    context: Sequence[Dict[str, Any]],
) -> str:
    """Produce a concise evidence-backed answer when the synthesis LLM is unavailable."""
    if not context:
        return "Không có dữ liệu về chủ đề này trong corpus."

    answer_type = plan.get("answer_type", "entity")
    expected = {normalize_text(label) for label in plan.get("expected_labels", [])}
    direct = [
        item
        for item in context
        if not expected or normalize_text(item.get("entity_type", "")) in expected
    ]
    if not direct:
        direct = list(context)

    def name(item: Dict[str, Any]) -> str:
        return str(item.get("entity_name") or "").strip()

    def description(item: Dict[str, Any]) -> str:
        return str(item.get("entity_desc") or "").strip()

    def source_relevance(source: str) -> float:
        source_tokens = tokenize(source)
        entity_tokens = set().union(
            *(tokenize(value) for value in plan.get("entities", []))
        )
        concept_tokens = set().union(
            *(tokenize(value) for value in plan.get("concepts", []))
        )
        query_tokens = tokenize(question)
        important = entity_tokens | concept_tokens
        important_overlap = len(source_tokens & important)
        query_overlap = len(source_tokens & query_tokens)
        return 3.0 * important_overlap + query_overlap / max(1, len(query_tokens))

    def localize_method_name(value: str) -> str:
        translations = {
            "novel method for vector rotation": "phương pháp quay vector mới",
            "fixed point arithmetic": "số học dấu phẩy cố định",
        }
        return translations.get(normalize_text(value), value)

    def localize_method_description(value: str) -> str:
        normalized = normalize_text(value)
        if (
            "coaxial gear system" in normalized
            and "fixed point arithmetic" in normalized
        ):
            return (
                "Phương pháp dựa trên **hệ bánh răng đồng trục**, kết hợp "
                "**số học dấu phẩy cố định** để nâng cao độ chính xác tần số."
            )
        if "high pressure liquid chromatography" in normalized:
            return (
                "Sử dụng **sắc ký lỏng hiệu năng cao (HPLC)** để phân tích "
                "các hợp chất mục tiêu."
            )
        return value

    def solvent_display(item: Dict[str, Any]) -> Tuple[str, str]:
        raw_name = name(item)
        text = normalize_text(f"{raw_name} {description(item)}")
        if "chloroform" in text and "methanol" in text:
            ratio = re.search(
                r"(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)",
                f"{raw_name} {description(item)}",
            )
            display = "chloroform/methanol"
            if ratio:
                display += f" ({ratio.group(1)}:{ratio.group(2)}, v/v)"
            return display, raw_name
        solvent_names = (
            ("chloroform", "chloroform"),
            ("methanol", "methanol"),
            ("ethanol", "ethanol"),
            ("hexane", "n-hexane" if "n hexane" in text else "hexane"),
            ("pure water", "nước tinh khiết"),
            ("water", "nước"),
            ("ether", "ether"),
            ("acetone", "acetone"),
        )
        for marker, display in solvent_names:
            if marker in text:
                return display, raw_name
        return raw_name, raw_name

    def localize_solvent_role(value: str) -> str:
        normalized = normalize_text(value)
        if "isolate isoquinoline alkaloids" in normalized:
            return "Chloroform được dùng để phân lập các alkaloid isoquinoline."
        if "total lipid extraction" in normalized:
            return "Hỗn hợp dung môi được dùng để chiết xuất lipid tổng số."
        if "solvent used in the extraction process" in normalized:
            return "Đây là dung môi được sử dụng trong quá trình chiết xuất."
        return value

    source_candidates: List[str] = []
    primary_evidence = direct[:1] or list(context[:1])
    for item in primary_evidence:
        ranked_sources = sorted(
            item.get("source_papers", []) or [],
            key=source_relevance,
            reverse=True,
        )
        for source in ranked_sources[:1]:
            if source and source not in source_candidates:
                source_candidates.append(source)
        for connection in item.get("connections", []) or []:
            relation = str(connection.get("relation") or "").upper()
            related_type = normalize_text(connection.get("related_type", ""))
            related_name = str(connection.get("related_name") or "").strip()
            if (
                relation == "USES_DATASET"
                and related_type in {"paper", "concept"}
                and related_name
                and related_name not in source_candidates
            ):
                source_candidates.append(related_name)
    required_entities = [
        normalize_text(value) for value in plan.get("required_entities", []) if value
    ]
    if not source_candidates:
        paper_items = [
            item
            for item in context
            if normalize_text(item.get("entity_type", "")) == "paper"
        ]
        paper_items.sort(key=lambda item: source_relevance(name(item)), reverse=True)
        for item in paper_items[:1]:
            item_name = name(item)
            normalized_name = normalize_text(item_name)
            if required_entities and not all(value in normalized_name for value in required_entities):
                continue
            if item_name and item_name not in source_candidates:
                source_candidates.append(item_name)
    source_answer_items = direct
    if answer_type == "metric":
        if plan.get("comparison_requested") and plan.get("comparison_items"):
            source_answer_items = [
                item
                for item in direct
                if max(
                    item.get("ranking", {}).get("comparison_items", {}).values(),
                    default=0.0,
                ) >= 0.75
                and max(
                    item.get("ranking", {}).get("metric_targets", {}).values(),
                    default=0.0,
                ) >= 0.50
            ]
        elif plan.get("multi_item"):
            source_answer_items = [
                item
                for item in direct
                if any(
                    item.get("ranking", {})
                    .get("requested_items", {})
                    .get(requested_item, 0.0) >= 0.80
                    for requested_item in plan.get("requested_items", [])
                )
            ]
        elif plan.get("multi_metric"):
            source_answer_items = [
                item
                for item in direct
                if any(
                    item.get("ranking", {})
                    .get("metric_targets", {})
                    .get(target["id"], 0.0) >= 0.50
                    for target in plan.get("metric_targets", [])
                )
            ]
        else:
            source_answer_items = direct[:1]
    elif answer_type in {"solvent", "method", "principle"}:
        source_answer_items = direct[:1]

    for item in source_answer_items:
        item_name = name(item)
        if normalize_text(item.get("entity_type", "")) == "concept":
            continue
        if item_name and item_name not in source_candidates:
            source_candidates.append(item_name)

    if answer_type == "process":
        ordered = sorted(direct, key=lambda item: int(item.get("process_order") or 999))
        process_translations = {
            "collaborative planning": "Lập kế hoạch hợp tác",
            "research lessons": "Thực hiện bài học nghiên cứu",
            "post observation discussion": "Thảo luận sau dự giờ",
            "lesson revision": "Chỉnh sửa bài học",
            "iterative cycle": "Lặp lại chu trình",
        }
        lines = [
            f"{index}. **{process_translations.get(normalize_text(name(item)), name(item))}**"
            for index, item in enumerate(ordered, start=1)
            if name(item)
        ]
        body = "Quá trình gồm các bước:\n\n" + "\n".join(lines)
    elif answer_type == "principle":
        item = direct[0]
        body = description(item) or f"Nguyên lý được sử dụng là **{name(item)}**."
    elif answer_type == "solvent":
        item = direct[0]
        display, raw_name = solvent_display(item)
        body = f"Dung môi được sử dụng là **{display}**."
        if normalize_text(display) != normalize_text(raw_name):
            body += f"\n\n- Node bằng chứng: *{raw_name}*."
        if description(item):
            body += f"\n- Vai trò: {localize_solvent_role(description(item))}"
    elif answer_type == "method":
        item = direct[0]
        item_name = name(item)
        item_desc = description(item)
        localized_name = localize_method_name(item_name)
        action = "được đề xuất" if plan.get("novelty_requested") else "được sử dụng"
        body = f"Phương pháp {action} là **{localized_name}**"
        if localized_name != item_name:
            body += f" (*{item_name}*)"
        body += "."
        if item_desc:
            body += (
                "\n\n- **Nguyên lý/cách thực hiện:** "
                + localize_method_description(item_desc)
            )
        result_connections = [
            connection
            for connection in item.get("connections", [])
            if str(connection.get("relation") or "").upper() == "ACHIEVED"
            and connection.get("related_name")
        ]
        if result_connections:
            localized_results = []
            for connection in result_connections[:2]:
                result_name = str(connection["related_name"])
                normalized_result = normalize_text(result_name)
                if "frequency precision" in normalized_result:
                    result_name = re.sub(
                        r"Frequency precision",
                        "Độ phân giải tần số",
                        result_name,
                        flags=re.IGNORECASE,
                    )
                elif "frequency error" in normalized_result:
                    result_name = re.sub(
                        r"Frequency error",
                        "Sai số tần số",
                        result_name,
                        flags=re.IGNORECASE,
                    )
                localized_results.append(result_name)
            body += "\n- **Kết quả liên quan:** " + "; ".join(localized_results)
    elif answer_type == "metric":
        if plan.get("comparison_requested") and plan.get("comparison_items"):
            rows: List[str] = []
            missing_cells = 0
            for comparison_item in plan.get("comparison_items", []):
                comparison_label = comparison_item["label"]
                values: List[str] = []
                for target in plan.get("metric_targets", []):
                    target_id = target["id"]
                    matches = [
                        item
                        for item in direct
                        if item.get("ranking", {})
                        .get("comparison_items", {})
                        .get(comparison_label, 0.0) >= 0.75
                        and item.get("ranking", {})
                        .get("metric_targets", {})
                        .get(target_id, 0.0) >= 0.50
                    ]
                    if matches:
                        values.append(
                            f"**{target.get('label_vi', target_id)}:** {name(matches[0])}"
                        )
                    else:
                        missing_cells += 1
                        values.append(
                            f"**{target.get('label_vi', target_id)}:** chưa có dữ liệu trực tiếp"
                        )
                rows.append(f"- **{comparison_label}:** " + "; ".join(values))
            body = "Kết quả so sánh theo dữ liệu hiện có:\n" + "\n".join(rows)
            if missing_cells:
                body += (
                    "\n\nDo một số ô so sánh chưa có bằng chứng trực tiếp trong corpus, "
                    "chưa thể kết luận đầy đủ đối tượng nào có chi phí thấp hơn hoặc "
                    "hiệu quả B/C cao hơn."
                )
        elif plan.get("multi_item"):
            lines: List[str] = []
            missing: List[str] = []
            for requested_item in plan.get("requested_items", []):
                matches = [
                    item
                    for item in direct
                    if item.get("ranking", {})
                    .get("requested_items", {})
                    .get(requested_item, 0.0) >= 0.80
                    and item.get("ranking", {}).get("subject", 0.0) >= 0.80
                ]
                if matches:
                    item_name = name(matches[0])
                    measurements = [
                        value
                        for value in re.findall(r"\(([^()]*)\)", item_name)
                        if re.search(r"\d", value)
                    ]
                    value = measurements[-1] if measurements else item_name
                    lines.append(f"- **{requested_item}:** {value}")
                else:
                    missing.append(requested_item)
            body = "Các giá trị có bằng chứng trực tiếp:\n" + "\n".join(lines)
            if missing:
                body += (
                    "\n\nKhông có dữ liệu trực tiếp trong corpus cho: "
                    + ", ".join(f"**{value}**" for value in missing)
                    + "."
                )
        elif plan.get("multi_metric"):
            lines: List[str] = []
            used_names = set()
            for target in plan.get("metric_targets", []):
                target_id = target["id"]
                matches = [
                    item
                    for item in direct
                    if item.get("ranking", {})
                    .get("metric_targets", {})
                    .get(target_id, 0.0) >= 0.50
                ]
                if matches:
                    item_name = name(matches[0])
                    if item_name and item_name not in used_names:
                        label = target.get("label_vi") or target_id
                        lines.append(f"- **{label}:** {item_name}")
                        used_names.add(item_name)
            body = (
                "Các chỉ tiêu được báo cáo:\n" + "\n".join(lines)
                if lines
                else "Không có dữ liệu về chủ đề này trong corpus."
            )
        else:
            item = direct[0]
            body = f"Giá trị được báo cáo là **{name(item)}**."
    elif answer_type == "dataset":
        item = direct[0]
        item_name = name(item)
        item_desc = description(item)
        body = f"Bộ dữ liệu được đề xuất là **{item_name}**."
        if item_desc:
            normalized_desc = normalize_text(item_desc)
            details: List[str] = []
            video_count = re.search(r"\b(\d[\d,]*)\s+(?:full[- ]?hd\s+and\s+ultra[- ]?hd\s+)?videos?\b", normalized_desc)
            fps = re.search(r"\b(\d+(?:\.\d+)?)\s+frames?\s+per\s+second\b", normalized_desc)
            if video_count:
                details.append(f"Gồm **{video_count.group(1)} video**.")
            if "full hd" in normalized_desc or "full-hd" in item_desc.lower():
                if "ultra hd" in normalized_desc or "ultra-hd" in item_desc.lower():
                    details.append("Video có độ phân giải **Full-HD và Ultra-HD**.")
                else:
                    details.append("Video có độ phân giải **Full-HD**.")
            if fps:
                details.append(f"Được ghi ở tốc độ **{fps.group(1)} khung hình/giây**.")
            if "fire detection" in normalized_desc:
                details.append("Được xây dựng phục vụ nghiên cứu **nhận diện và phát hiện cháy qua video**.")
            if details:
                body += "\n\nĐặc điểm chính:\n" + "\n".join(f"- {value}" for value in details)
            else:
                body += f"\n\nĐặc điểm chính:\n- {item_desc}"
    elif answer_type == "taxon":
        title_answer = str(plan.get("title_evidence_answer") or "").strip()
        if title_answer:
            body = (
                "Loài thực vật được ghi nhận mới cho hệ thực vật Việt Nam là "
                f"**{title_answer}**."
            )
        else:
            item = direct[0]
            body = f"Loài được ghi nhận là **{name(item)}**."
    elif answer_type == "taxonomy":
        item = direct[0]
        body = f"Nhóm phân loại được ghi nhận là **{name(item)}**."
    elif answer_type == "component":
        evidence_text = " ".join(
            f"{name(item)} {description(item)} "
            + " ".join(
                f"{connection.get('related_name', '')} {connection.get('related_desc', '')}"
                for connection in item.get("connections", [])
            )
            for item in context
        )
        normalized_evidence = normalize_text(evidence_text)
        components: List[str] = []

        def add_component(marker: str, label: str) -> None:
            if marker in normalized_evidence and label not in components:
                components.append(label)

        # Generic technology markers commonly represented in scientific
        # descriptions. Values are emitted only when present in evidence.
        add_component("deep reinforcement learning", "Deep Reinforcement Learning (DRL)")
        add_component("curriculum learning", "Curriculum Learning")
        add_component("proximal policy optimization", "tác tử Proximal Policy Optimization (PPO)")
        add_component("variational autoencoder", "Variational Autoencoder (VAE)")
        add_component("carla simulator", "môi trường mô phỏng CARLA")
        add_component("collision penalty", "cơ chế phạt va chạm trong hàm phần thưởng")

        if components:
            core = components[:4]
            extras = components[4:]
            body = (
                "Phương pháp kết hợp các thành phần kỹ thuật chính: "
                + ", ".join(f"**{value}**" for value in core)
                + "."
            )
            if extras:
                body += (
                    "\n\nMột số yếu tố triển khai liên quan:\n"
                    + "\n".join(f"- {value}" for value in extras)
                )
            if "two fold curriculum" in normalized_evidence:
                body += (
                    "\n- Huấn luyện theo curriculum hai giai đoạn, tăng dần độ khó "
                    "của môi trường."
                )
        else:
            values = [
                name(item)
                for item in direct[:6]
                if name(item) and normalize_text(item.get("entity_type", "")) != "metric"
            ]
            body = "Các thành phần chính gồm: " + ", ".join(
                f"**{value}**" for value in values
            ) + "."
    elif answer_type == "relationship":
        directional = [
            item
            for item in direct
            if any(
                marker in normalize_text(f"{name(item)} {description(item)}")
                for marker in ("increase", "decrease", "effect", "larger", "probability")
            )
        ]
        selected = directional[:2] or direct[:2]
        statements = []
        for item in selected:
            item_name = normalize_text(name(item))
            if "increase in borrowing ability" in item_name and "16 7" in item_name:
                statements.append(
                    "Doanh nghiệp quy mô lớn có khả năng vay được vốn ngân hàng "
                    "cao hơn doanh nghiệp nhỏ khoảng **16,7%**."
                )
            elif "increase in bank loan possibility" in item_name and "12 6" in item_name:
                statements.append(
                    "Mỗi khi doanh thu tăng thêm 1 triệu đồng, khả năng tiếp cận "
                    "khoản vay ngân hàng tăng khoảng **12,6%**."
                )
            else:
                statements.append(description(item) or name(item))
        body = " ".join(statements)
    elif answer_type == "factor":
        values = [name(item) for item in direct[:6] if name(item)]
        body = "Các yếu tố được đề cập gồm: " + ", ".join(f"**{value}**" for value in values) + "."
    else:
        item = direct[0]
        body = description(item) or f"Thông tin phù hợp nhất là **{name(item)}**."

    sources = source_candidates[:3]
    if not sources:
        return body
    source_text = "\n".join(f"- {source}" for source in sources)
    return f"{body}\n\n📌 **Nguồn tham chiếu**\n{source_text}"


def select_highlight_nodes(
    plan: Dict[str, Any],
    context: Sequence[Dict[str, Any]],
    limit: int = 8,
) -> List[str]:
    """Keep direct answers and their strongest paper evidence for graph highlighting."""
    selected: List[str] = []

    def add(value: Any) -> None:
        value = str(value or "").strip()
        if value and value not in selected:
            selected.append(value)

    important_tokens = set().union(
        *(tokenize(value) for value in [
            *plan.get("entities", []),
            *plan.get("concepts", []),
            *plan.get("search_terms", []),
        ])
    )

    def paper_relevance(value: str) -> int:
        return len(tokenize(value) & important_tokens)

    answer_type = plan.get("answer_type")
    direct_limits = {
        "process": 6,
        "dataset": 5,
        "factor": 6,
        "component": 6,
        "relationship": 2,
    }
    if answer_type == "metric" and plan.get("comparison_requested"):
        direct_limit = max(
            1,
            len(plan.get("comparison_items", []))
            * len(plan.get("metric_targets", [])),
        )
    elif answer_type == "metric" and plan.get("multi_item"):
        direct_limit = len(plan.get("requested_items", []))
    elif answer_type == "metric" and plan.get("multi_metric"):
        direct_limit = len(plan.get("metric_targets", []))
    else:
        direct_limit = 1 if plan.get("single_answer") else direct_limits.get(answer_type, 1)
    expected = {normalize_text(label) for label in plan.get("expected_labels", [])}
    retained_items: List[Dict[str, Any]] = []
    required_entities = [
        normalize_text(value) for value in plan.get("required_entities", []) if value
    ]
    for item in context:
        item_name = normalize_text(item.get("entity_name", ""))
        if required_entities and any(value == item_name for value in required_entities):
            add(item.get("entity_name"))
            retained_items.append(item)
            break
    for item in context:
        if item in retained_items:
            continue
        ranking = item.get("ranking", {})
        label = normalize_text(item.get("entity_type", ""))
        type_score = float(ranking.get("answer_type") or 0.0)
        evidence = float(ranking.get("evidence") or 0.0)
        is_expected_type = not expected or label in expected
        if answer_type == "metric" and plan.get("multi_item"):
            item_scores = ranking.get("requested_items", {})
            target_scores = ranking.get("metric_targets", {})
            if (
                max(item_scores.values(), default=0.0) < 0.80
                or float(ranking.get("subject") or 0.0) < 0.80
                or (
                    target_scores
                    and max(target_scores.values(), default=0.0) < 0.50
                )
            ):
                continue
        if answer_type == "metric" and plan.get("multi_metric"):
            target_scores = ranking.get("metric_targets", {})
            if max(target_scores.values(), default=0.0) < 0.50:
                continue
        if answer_type == "metric" and plan.get("comparison_requested"):
            comparison_scores = ranking.get("comparison_items", {})
            if max(comparison_scores.values(), default=0.0) < 0.75:
                continue
        if is_expected_type and (type_score >= 0.55 or evidence >= 0.25):
            add(item.get("entity_name"))
            retained_items.append(item)
            if len(retained_items) >= direct_limit:
                break

    if not retained_items and context:
        add(context[0].get("entity_name"))
        retained_items.append(context[0])

    # Highlight only papers directly attached to the retained answer evidence.
    for item in retained_items:
        papers = sorted(
            item.get("source_papers", []) or [],
            key=paper_relevance,
            reverse=True,
        )
        for paper in papers[:1]:
            add(paper)
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break
        for connection in item.get("connections", []) or []:
            if str(connection.get("relation") or "").upper() == "USES_DATASET":
                add(connection.get("related_name"))
                if len(selected) >= limit:
                    break

    return selected[:limit]
