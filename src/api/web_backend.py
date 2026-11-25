from src.extraction.prompt_library import SYSTEM_INSTRUCTION, PROMPT_VERSION, build_user_prompt
from src.extraction.reextract_review import sections_from_document, validate_extraction, schema
import os
import re
import json
import logging
import requests
import fitz
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from neo4j import GraphDatabase
from graph_connection import graph_session

logger = logging.getLogger(__name__)

try:
    from config import GEMINI_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
except ImportError:
    GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
    NEO4J_URI       = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER      = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD  = os.getenv("NEO4J_PASSWORD", "")

GROBID_URL = os.getenv("GROBID_URL", "http://localhost:8070/api/processFulltextDocument")

gemini_client = genai.Client(api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)))


# ---------------------------------------------------------------------------
# 3. PROMPT CẢI TIẾN
# ---------------------------------------------------------------------------

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\[\d+(?:[,-]\s*\d+)*\]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_entity_name(name):
    if not name:
        return ""
    name = str(name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name

def parse_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    raw_header = ""

    try:
        doc = fitz.open(pdf_path)
        raw_header = doc[0].get_text("text")[:2000]
        doc.close()
    except:
        pass

    try:
        with open(pdf_path, 'rb') as f:
            response = requests.post(GROBID_URL, files={'input': f}, timeout=300)
        if response.status_code != 200:
            return None
        xml_content = response.text
    except:
        return None

    soup = BeautifulSoup(xml_content, 'xml')

    paper_data = {
        "filename": filename,
        "title": "",
        "raw_header": clean_text(raw_header),
        "abstract": "",
        "sections": []
    }

    title_tag = soup.find('title', type='main')
    if title_tag:
        paper_data["title"] = clean_text(title_tag.get_text())

    abstract_tag = soup.find('abstract')
    if abstract_tag:
        paper_data["abstract"] = clean_text(abstract_tag.get_text())

    body = soup.find('body')
    if body:
        for div in body.find_all('div'):
            head = div.find('head')
            if not head:
                continue

            title = head.get_text(strip=True)
            paragraphs = div.find_all('p')
            content = " ".join(p.get_text(strip=True) for p in paragraphs)
            content = clean_text(content)

            if len(content) > 30:
                paper_data["sections"].append({
                    "section_title": title,
                    "content": content
                })

    from src.extraction.pdf_source import attach_pdf_pages
    return attach_pdf_pages(paper_data,pdf_path)

def prepare_content(paper_data):
    parts = []

    if paper_data.get("title"):
        parts.append(f"PAPER TITLE: {paper_data['title']}")

    if paper_data.get("raw_header"):
        parts.append(
            "--- Header Information ---\n"
            + paper_data["raw_header"]
        )

    if paper_data.get("abstract"):
        parts.append(f"ABSTRACT:\n{paper_data['abstract']}")

    for sec in paper_data.get("sections", []):
        content = sec.get("content", "")
        if len(content) > 50:
            parts.append(f"SECTION: {sec['section_title']}\n{content}")

    return "\n\n".join(parts)


def extract_knowledge(paper_data):
    from src.extraction.strict_runner import SYSTEM,VERSION,policy,request_prompt,evaluate
    from src.extraction.evidence_catalog import build_catalog
    from src.extraction.workflow_io import canonical_hash,loads
    from src.extraction.source_quality import quality_report
    try:
        sections=sections_from_document(paper_data)
        catalog=build_catalog(sections)
        contract,_=policy()
        response=gemini_client.models.generate_content(
            model="gemini-2.5-flash",contents=request_prompt(catalog,sections),
            config=types.GenerateContentConfig(system_instruction=SYSTEM,
                response_mime_type="application/json",response_schema=contract['schema'],
                temperature=0,max_output_tokens=16384,thinking_config={"thinking_budget":0}))
        # The SDK may return partial text. Never promote a truncated response.
        candidates=getattr(response,"candidates",None)
        if not candidates:raise ValueError("No complete model candidate")
        finish=getattr(candidates[0],"finish_reason",None)
        if str(getattr(finish,"value",finish))!="STOP":raise ValueError("Incomplete model response")
        result,issues,blockers=evaluate(loads(response.text),catalog,sections)
        return {"filename":paper_data["filename"],"paper_title":paper_data.get("title",""),
            "title":paper_data.get("title",""),"abstract":paper_data.get("abstract",""),
            "source_sha256":canonical_hash(paper_data),"source_hash_kind":"canonical_parsed_document",
            "sections_sha256":catalog['sections_sha256'],"protocol_id":VERSION,
            "policy_sha256":canonical_hash(contract),"extraction_result":result,
            "candidate_status":"quarantined" if issues else "pending_semantic_review",
            "validation_issues":issues,"blocking_issues":blockers,"source_quality":quality_report(paper_data),
            "model_metadata":{"model_version":getattr(response,"model_version",None)}}
    except Exception as exc:
        logger.error("Extraction failed (%s); no graph import",type(exc).__name__)
        return None


def save_to_neo4j(data):
    # Shared importer prevents untyped edges and partial-paper writes.
    from src.graph_construction.build_graph import KnowledgeGraphBuilder
    from src.extraction.graph_policy import require_graph_review
    require_graph_review(data)
    builder=KnowledgeGraphBuilder(NEO4J_URI,NEO4J_USER,NEO4J_PASSWORD)
    try:
        return builder.load_paper_data(data)
    finally:
        builder.close()


def clear_graph():
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    with graph_session(driver) as session:
        session.run("MATCH (n) DETACH DELETE n")
    driver.close()
