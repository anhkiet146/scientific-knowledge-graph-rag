import runpy
from pathlib import Path
if __name__=="__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1]/"src/graph_construction/build_graph.py"),run_name="__main__")
