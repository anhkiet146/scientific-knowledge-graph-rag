"""
database_mongo.py — v3
Thêm:
- Collection `extraction_results`: lưu entities/relations sau extract (trước khi commit Neo4j)
- Collection `sessions`: metadata cuộc trò chuyện (title, created_at, last_active)
- add_to_queue nhận file_id từ caller (không tự sinh nữa)
- delete_queue_item(): xóa file khỏi queue + xóa extraction result
- save_extraction_result / get_extraction_result
- create_session / list_sessions / get_session_meta / delete_session / touch_session / rename_session
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)


class MongoManager:
    def __init__(self, uri: str = "mongodb://localhost:27017/", max_retries: int = 3):
        self.uri    = uri
        self.client = self._connect(max_retries)
        self.db     = self.client["graphrag_db"]

        self.messages            = self.db["chat_history"]
        self.upload_queue        = self.db["upload_queue"]
        self.extraction_results  = self.db["extraction_results"]
        self.sessions_col        = self.db["sessions"]

        self._ensure_indexes()

    # ── Connection ─────────────────────────────────────────────────────────────
    def _connect(self, max_retries: int) -> MongoClient:
        for attempt in range(max_retries):
            try:
                client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
                client.admin.command("ping")
                logger.info("MongoDB connected")
                return client
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.warning(f"MongoDB attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        logger.error("MongoDB connect failed; using unverified client")
        return MongoClient(self.uri)

    def _ensure_indexes(self):
        try:
            self.messages.create_index([("session_id", ASCENDING), ("timestamp", ASCENDING)])

            ttl_seconds = 30 * 24 * 3600
            timestamp_index = self.messages.index_information().get("timestamp_1")
            if timestamp_index and timestamp_index.get("expireAfterSeconds") != ttl_seconds:
                self.db.command({
                    "collMod": self.messages.name,
                    "index": {
                        "name": "timestamp_1",
                        "expireAfterSeconds": ttl_seconds,
                    },
                })
                logger.info("MongoDB TTL index updated to %s seconds", ttl_seconds)
            else:
                self.messages.create_index("timestamp", expireAfterSeconds=ttl_seconds)

            self.upload_queue.create_index([("file_id", ASCENDING)], unique=True)
            self.upload_queue.create_index([("timestamp", DESCENDING)])
            self.extraction_results.create_index([("file_id", ASCENDING)], unique=True)
            self.sessions_col.create_index([("last_active", DESCENDING)])
        except Exception as e:
            logger.warning(f"Index warning: {e}")
    # ════════════════════════════════════════════════════════════════════════
    # UPLOAD QUEUE
    # ════════════════════════════════════════════════════════════════════════

    def add_to_queue(self, filename: str, file_id: str, file_size: int = 0, mime_type: str = "application/pdf") -> str:
        """Thêm file vào queue. file_id do caller cấp."""
        self.upload_queue.insert_one({
            "file_id":    file_id,
            "name":       filename,
            "status":     "pending",
            "progress":   0,
            "entities":   0,
            "relations":  0,
            "file_size":  file_size,
            "mime_type":  mime_type,
            "error_msg":  None,
            "timestamp":  datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        return file_id

    def update_queue_status(self, file_id: str, status: str, progress: int = 0,
                             entities: int = 0, relations: int = 0, error_msg: str = None):
        update = {
            "status": status, "progress": progress,
            "entities": entities, "relations": relations,
            "updated_at": datetime.utcnow(),
        }
        if error_msg:
            update["error_msg"] = error_msg
        if status in ("committed", "extracted"):
            update["completed_at"] = datetime.utcnow()
        self.upload_queue.update_one({"file_id": file_id}, {"$set": update})

    def get_queue(self, limit: int = 30) -> list:
        cursor = self.upload_queue.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit)
        results = []
        for doc in cursor:
            for field in ("timestamp", "updated_at", "completed_at"):
                if isinstance(doc.get(field), datetime):
                    doc[field] = doc[field].isoformat()
            results.append(doc)
        return results

    def get_file_by_id(self, file_id: str) -> dict | None:
        return self.upload_queue.find_one({"file_id": file_id}, {"_id": 0})

    def delete_queue_item(self, file_id: str) -> bool:
        """Xóa 1 file khỏi queue và extraction result. Returns True nếu xóa được."""
        r = self.upload_queue.delete_one({"file_id": file_id})
        self.extraction_results.delete_one({"file_id": file_id})
        return r.deleted_count > 0

    def get_queue_stats(self) -> dict:
        result = list(self.upload_queue.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}]))
        stats  = {r["_id"]: r["count"] for r in result}
        return {k: stats.get(k, 0) for k in ("total", "pending", "extracting", "extracted", "committed", "error")} | {"total": sum(stats.values())}

    # ════════════════════════════════════════════════════════════════════════
    # EXTRACTION RESULTS (preview trước khi commit Neo4j)
    # ════════════════════════════════════════════════════════════════════════

    def save_extraction_result(self, file_id: str, title: str, abstract: str,
                                entities: list, relations: list):
        """Lưu kết quả extract vào MongoDB. Upsert theo file_id."""
        self.extraction_results.replace_one(
            {"file_id": file_id},
            {
                "file_id":   file_id,
                "title":     title,
                "abstract":  abstract,
                "entities":  entities,
                "relations": relations,
                "saved_at":  datetime.utcnow(),
            },
            upsert=True,
        )

    def get_extraction_result(self, file_id: str) -> dict | None:
        doc = self.extraction_results.find_one({"file_id": file_id}, {"_id": 0})
        if doc and isinstance(doc.get("saved_at"), datetime):
            doc["saved_at"] = doc["saved_at"].isoformat()
        return doc

    # ════════════════════════════════════════════════════════════════════════
    # SESSIONS (lịch sử cuộc trò chuyện)
    # ════════════════════════════════════════════════════════════════════════

    def create_session(self, session_id: str, title: str):
        now = datetime.utcnow()
        self.sessions_col.update_one(
            {"session_id": session_id},
            {"$setOnInsert": {"session_id": session_id, "title": title, "created_at": now, "last_active": now}},
            upsert=True,
        )

    def list_sessions(self) -> list:
        """Liệt kê sessions, mới nhất trước. Kèm số lượng tin nhắn."""
        cursor = self.sessions_col.find({}, {"_id": 0}).sort("last_active", DESCENDING).limit(50)
        results = []
        for s in cursor:
            for field in ("created_at", "last_active"):
                if isinstance(s.get(field), datetime):
                    s[field] = s[field].isoformat()
            # Đếm số message trong session
            s["message_count"] = self.messages.count_documents({"session_id": s["session_id"]})
            results.append(s)
        return results

    def get_session_meta(self, session_id: str) -> dict | None:
        doc = self.sessions_col.find_one({"session_id": session_id}, {"_id": 0})
        if doc:
            for field in ("created_at", "last_active"):
                if isinstance(doc.get(field), datetime):
                    doc[field] = doc[field].isoformat()
        return doc

    def touch_session(self, session_id: str):
        """Cập nhật last_active."""
        self.sessions_col.update_one(
            {"session_id": session_id},
            {"$set": {"last_active": datetime.utcnow()}},
        )

    def rename_session(self, session_id: str, title: str):
        self.sessions_col.update_one({"session_id": session_id}, {"$set": {"title": title}})

    def delete_session(self, session_id: str):
        self.sessions_col.delete_one({"session_id": session_id})

    # ════════════════════════════════════════════════════════════════════════
    # CHAT HISTORY
    # ════════════════════════════════════════════════════════════════════════

    def save_chat_message(self, session_id: str, role: str, content: str,
                           highlight_nodes: list = None, metadata: dict = None):
        self.messages.insert_one({
            "session_id":      session_id,
            "role":            role,
            "content":         content,
            "highlight_nodes": highlight_nodes or [],
            "metadata":        metadata or {},
            "timestamp":       datetime.utcnow(),
        })

    def get_chat_history(self, session_id: str, limit: int = 200) -> list:
        cursor = (
            self.messages
            .find({"session_id": session_id}, {"_id": 0})
            .sort("timestamp", ASCENDING)
            .limit(limit)
        )
        return list(cursor)

    def clear_chat_history(self, session_id: str) -> int:
        r = self.messages.delete_many({"session_id": session_id})
        return r.deleted_count