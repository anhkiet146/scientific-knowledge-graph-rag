"""Explicit development-only chunk runner; default API budget is two calls."""
import runpy
import sys
from pathlib import Path
if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'src/extraction/chunk_runner.py'
    sys.path.insert(0,str(path.parent))
    runpy.run_path(str(path),run_name='__main__')
