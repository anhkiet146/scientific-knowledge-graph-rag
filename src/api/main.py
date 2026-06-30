"""
main.py — GraphRAG Studio API v3
Thay đổi:
- Upload chỉ parse + extract, KHÔNG tự nạp vào Neo4j
- POST /api/upload/{file_id}/commit  → người dùng bấm mới nạp vào Neo4j
- GET  /api/upload/{file_id}/preview → xem entities/relations đã trích xuất
- DELETE /api/upload/{file_id}       → xóa file khỏi hàng đợi
- GET  /api/sessions                 → liệt kê tất cả session (lịch sử chat)
- POST /api/sessions                 → tạo session mới
- DELETE /api/chat/{session_id}      → xóa 1 cuộc trò chuyện
- GET  /api/sessions/{session_id}/meta → lấy tên + thời gian tạo session
"""

import os
import uuid
import logging
import tempfile
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase

from database_mongo import MongoManager
from graphrag_engine import ask_graphrag, get_followup_suggestions

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GraphRAG Studio API", version="3.0.0")
db  = MongoManager()

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(tempfile.gettempdir(), "graphrag_uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ── Request models ─────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    session_id: str
    question: str
    scope: str = "all"

class CreateSessionRequest(BaseModel):
    title: Optional[str] = None   # tên cuộc trò chuyện (tuỳ chọn)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: UPLOAD — chỉ extract, chưa commit vào Neo4j
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_only_background(file_id: str, file_path: str, original_name: str):
    """
    Chạy ngầm: parse PDF + extract knowledge → lưu kết quả vào MongoDB.
    KHÔNG nạp vào Neo4j.
    """
    try:
        logger.info(f"[{file_id}] Extract-only pipeline: {original_name}")
        db.update_queue_status(file_id, "extracting", progress=15)

        from web_backend import parse_pdf
        paper_data = parse_pdf(file_path)
        if not paper_data:
            raise ValueError("PDF parsing failed")
        db.update_queue_status(file_id, "extracting", progress=45)

        from web_backend import extract_knowledge
        knowledge = extract_knowledge(paper_data)
        if not knowledge:
            raise ValueError("Knowledge extraction failed")

        # Lưu kết quả extraction vào MongoDB (để preview & commit sau)
        entities  = knowledge["extraction_result"].get("entities",  [])
        relations = knowledge["extraction_result"].get("relations", [])

        db.save_extraction_result(
            file_id    = file_id,
            title      = knowledge.get("title", original_name),
            abstract   = knowledge.get("abstract", ""),
            entities   = entities,
            relations  = relations,
        )

        db.update_queue_status(
            file_id,
            status    = "extracted",   # ← trạng thái mới: đã extract, chờ commit
            progress  = 100,
            entities  = len(entities),
            relations = len(relations),
        )
        logger.info(f"[{file_id}] Extraction done: {len(entities)} entities, {len(relations)} relations")

    except Exception as e:
        logger.error(f"[{file_id}] Extract error: {e}")
        db.update_queue_status(file_id, "error", progress=0, error_msg=str(e))
    finally:
        # Giữ file tạm trong UPLOAD_DIR để có thể retry nếu cần
        pass


@app.post("/api/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload 1 file PDF/JSON — chỉ extract, CHƯA nạp Neo4j."""
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in {".pdf", ".json"}:
        raise HTTPException(400, f"Chỉ hỗ trợ PDF và JSON. Nhận: {ext}")

    file_id  = str(uuid.uuid4())
    tmp_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    content  = await file.read()

    with open(tmp_path, "wb") as f:
        f.write(content)

    file_size = len(content)
    db.add_to_queue(file.filename or "unknown", file_id=file_id, file_size=file_size)
    background_tasks.add_task(_extract_only_background, file_id, tmp_path, file.filename or "unknown")

    return {"status": "queued", "file_id": file_id, "filename": file.filename}


@app.post("/api/upload/batch")
async def upload_batch(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Upload nhiều file — chỉ extract, CHƯA nạp Neo4j."""
    results = []
    for file in files:
        ext = os.path.splitext(file.filename or "")[-1].lower()
        if ext not in {".pdf", ".json"}:
            results.append({"filename": file.filename, "status": "skipped"})
            continue

        file_id  = str(uuid.uuid4())
        tmp_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        content  = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        db.add_to_queue(file.filename or "unknown", file_id=file_id, file_size=len(content))
        background_tasks.add_task(_extract_only_background, file_id, tmp_path, file.filename or "unknown")
        results.append({"filename": file.filename, "status": "queued", "file_id": file_id})

    return {"results": results, "total": len(files)}


@app.get("/api/upload/queue")
def get_queue():
    return db.get_queue()


@app.get("/api/upload/{file_id}/preview")
def preview_extraction(file_id: str):
    """
    Trả về entities + relations đã trích xuất của 1 file,
    để người dùng xem trước khi commit vào Neo4j.
    """
    data = db.get_extraction_result(file_id)
    if not data:
        raise HTTPException(404, "Không tìm thấy kết quả extraction cho file này.")
    return data


@app.post("/api/upload/{file_id}/commit")
def commit_to_neo4j(file_id: str):
    """
    Người dùng bấm nút "Nạp vào Neo4j" → lấy kết quả đã extract và lưu vào graph.
    """
    data = db.get_extraction_result(file_id)
    if not data:
        raise HTTPException(404, "Không tìm thấy kết quả extraction. Hãy upload và chờ extract xong.")

    file_info = db.get_file_by_id(file_id)
    if not file_info:
        raise HTTPException(404, "Không tìm thấy file trong hàng đợi.")

    status = file_info.get("status", "")
    if status == "committed":
        raise HTTPException(400, "File này đã được nạp vào Neo4j rồi.")
    if status not in ("extracted",):
        raise HTTPException(400, f"File chưa sẵn sàng (status: {status}). Vui lòng chờ extraction xong.")

    try:
        from web_backend import save_to_neo4j
        knowledge_payload = {
            "filename":  file_info["name"],
            "title":     data.get("title", file_info["name"]),
            "abstract":  data.get("abstract", ""),
            "extraction_result": {
                "entities":  data.get("entities",  []),
                "relations": data.get("relations", []),
            },
        }
        stats = save_to_neo4j(knowledge_payload)
        db.update_queue_status(
            file_id,
            status    = "committed",
            progress  = 100,
            entities  = stats.get("entities_saved",  0),
            relations = stats.get("relations_saved", 0),
        )
        logger.info(f"[{file_id}] Committed to Neo4j: {stats}")
        return {"status": "committed", "entities_saved": stats["entities_saved"], "relations_saved": stats["relations_saved"]}

    except Exception as e:
        logger.error(f"[{file_id}] Commit error: {e}")
        raise HTTPException(500, f"Lỗi nạp vào Neo4j: {str(e)}")


@app.delete("/api/upload/{file_id}")
def delete_from_queue(file_id: str):
    """Xóa 1 file khỏi hàng đợi (xóa cả extraction result và file tạm)."""
    deleted = db.delete_queue_item(file_id)
    if not deleted:
        raise HTTPException(404, "Không tìm thấy file.")

    # Dọn file tạm nếu còn
    for ext in (".pdf", ".json"):
        tmp = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass

    return {"status": "deleted", "file_id": file_id}


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: GRAPH EXPLORER
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/graph")
def get_dynamic_graph(search: Optional[str] = None, limit: int = 200):
    driver = get_neo4j_driver()
    nodes, links, node_ids = [], [], set()
    with driver.session() as session:
        if search and search.strip():
            query = """
            MATCH (n)
            WHERE toLower(coalesce(n.name, n.id, n.title, '')) CONTAINS toLower($search)
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n, type(r) AS rel_type, m LIMIT 300
            """
            result = session.run(query, search=search.strip())
        else:
            result = session.run(
                "MATCH (n)-[r]->(m) RETURN n, type(r) AS rel_type, m LIMIT $limit",
                limit=limit,
            )
        for record in result:
            n, rel_type, m = record["n"], record["rel_type"], record["m"]
            n_id  = n.get("name", n.get("id", n.get("title", "Unknown")))
            n_lbl = list(n.labels)[0] if n.labels else "Unknown"
            if n_id not in node_ids:
                nodes.append({"id": n_id, "group": n_lbl, "val": 15, "description": n.get("description", "")})
                node_ids.add(n_id)
            if m:
                m_id  = m.get("name", m.get("id", m.get("title", "Unknown")))
                m_lbl = list(m.labels)[0] if m.labels else "Unknown"
                if m_id not in node_ids:
                    nodes.append({"id": m_id, "group": m_lbl, "val": 15, "description": m.get("description", "")})
                    node_ids.add(m_id)
                links.append({"source": n_id, "target": m_id, "name": rel_type or ""})
    driver.close()
    return {"nodes": nodes, "links": links}


@app.get("/api/graph/stats")
def get_graph_stats():
    driver = get_neo4j_driver()
    with driver.session() as session:
        nc = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        ec = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    driver.close()
    return {"nodes": nc, "edges": ec}


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: ENTITY TABLE
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/entities")
def get_entities_table(entity_type: Optional[str] = None, min_rels: int = 0, limit: int = 8000):
    driver = get_neo4j_driver()
    label_filter = "IN ['Paper','Document','Article']" if not entity_type else f"= '{entity_type}'"
    data = []
    with driver.session() as session:
        result = session.run(f"""
            MATCH (n)
            WHERE labels(n)[0] {label_filter}
            OPTIONAL MATCH (n)-[r]-()
            WITH labels(n)[0] AS type,
                 n.name AS n_name, n.id AS n_id, n.title AS n_title, n.filename AS n_filename,
                 count(r) AS rel_count
            WHERE rel_count >= $min_rels
            RETURN type, n_name, n_id, n_title, n_filename, rel_count
            ORDER BY rel_count DESC LIMIT $limit
        """, min_rels=min_rels, limit=limit)

        for r in result:
            # Ưu tiên lấy thuộc tính chứa tên (từ trái qua phải)
            raw_name = r["n_name"] or r["n_id"] or r["n_title"] or r["n_filename"]

            # Làm sạch chuỗi: loại bỏ toàn bộ khoảng trắng, dấu tab, dấu xuống dòng thừa
            clean_name = str(raw_name).strip() if raw_name else ""

            # Nếu chuỗi sau khi làm sạch bị rỗng, ép buộc dùng tên file (filename)
            if not clean_name:
                clean_name = str(r["n_filename"]).strip() if r["n_filename"] else "Unknown Document"

            data.append({"name": clean_name, "type": r["type"], "rels": r["rel_count"]})

    driver.close()
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/analytics")
def get_analytics():
    driver = get_neo4j_driver()
    stats = {"nodes_by_label": {}, "relations_by_type": {}, "top_entities": []}
    with driver.session() as session:
        for r in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"):
            if r["label"]: stats["nodes_by_label"][r["label"]] = r["count"]
        for r in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"):
            if r["type"]: stats["relations_by_type"][r["type"]] = r["count"]
        for r in session.run("MATCH (n)-[r]-() RETURN labels(n)[0] AS type, coalesce(n.name, n.title) AS name, count(r) AS c ORDER BY c DESC LIMIT 10"):
            if r["name"]: stats["top_entities"].append({"n": r["name"], "t": r["type"], "c": r["c"]})
    driver.close()
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: ASK THE GRAPH — multi-session
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/sessions")
def list_sessions():
    """Liệt kê tất cả cuộc trò chuyện (session), mới nhất trước."""
    return db.list_sessions()


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    """Tạo cuộc trò chuyện mới. Trả về session_id."""
    session_id = str(uuid.uuid4())
    title = req.title or f"Cuộc trò chuyện {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
    db.create_session(session_id, title)
    return {"session_id": session_id, "title": title}


@app.get("/api/sessions/{session_id}/meta")
def get_session_meta(session_id: str):
    meta = db.get_session_meta(session_id)
    if not meta:
        raise HTTPException(404, "Session không tồn tại.")
    return meta


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, req: CreateSessionRequest):
    """Đổi tên cuộc trò chuyện."""
    db.rename_session(session_id, req.title or "Untitled")
    return {"status": "ok"}


@app.post("/api/ask")
async def ask_the_graph(req: AskRequest, background_tasks: BackgroundTasks):
    loop = asyncio.get_event_loop()

    # Lấy lịch sử hội thoại gần đây (tối đa 6 tin nhắn)
    try:
        raw_history = db.get_chat_history(req.session_id)
        history = [{"role": h["role"], "content": h["content"]} for h in raw_history[-6:]]
    except Exception:
        history = []

    # Chạy graphrag (blocking) trong thread pool
    answer, source_nodes, timings = await loop.run_in_executor(
        executor, ask_graphrag, req.question, req.scope, history
    )

    # Save + followup chạy background — không block response
    background_tasks.add_task(db.save_chat_message, req.session_id, "user", req.question)
    background_tasks.add_task(db.save_chat_message, req.session_id, "assistant", answer, source_nodes)
    background_tasks.add_task(db.touch_session, req.session_id)

    # Trả về ngay, không chờ followup
    return {"answer": answer, "highlight_nodes": source_nodes, "followup_suggestions": [], "timings": timings}


@app.get("/api/chat/{session_id}")
def get_chat_history(session_id: str):
    return [
        {"role": h["role"], "content": h["content"], "highlight_nodes": h.get("highlight_nodes", [])}
        for h in db.get_chat_history(session_id)
    ]


@app.delete("/api/chat/{session_id}")
def delete_session(session_id: str):
    """Xóa toàn bộ cuộc trò chuyện (messages + session meta)."""
    db.clear_chat_history(session_id)
    db.delete_session(session_id)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health_check():
    neo4j_ok = mongo_ok = False
    try:
        d = get_neo4j_driver(); d.verify_connectivity(); d.close(); neo4j_ok = True
    except Exception: pass
    try:
        db.client.admin.command("ping"); mongo_ok = True
    except Exception: pass
    return {"status": "ok" if (neo4j_ok and mongo_ok) else "degraded", "neo4j": neo4j_ok, "mongodb": mongo_ok}
