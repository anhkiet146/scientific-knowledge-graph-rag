"""Start the legacy API with explicit module paths from any working directory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "src/api", ROOT / "src/retrieval"):
    sys.path.insert(0, str(folder))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
