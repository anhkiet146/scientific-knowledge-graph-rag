"""Local runtime configuration. Credentials are never stored in this module."""
import os
import json
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if os.getenv("GEMINI_KEYS_FILE"):
    data = json.loads(Path(os.environ["GEMINI_KEYS_FILE"]).read_text(encoding="utf-8-sig"))
    GEMINI_API_KEY = data.get("api_key") or data.get("keys", {}).get(data.get("active", ""), "")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.5")
