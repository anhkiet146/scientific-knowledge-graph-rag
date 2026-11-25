"""Default launcher for the strict evidence-ID candidate workflow."""
import os
import runpy
import sys
from pathlib import Path
if __name__=="__main__":
    root=Path(__file__).resolve().parents[2]
    if not any(a=="--input" or a.startswith("--input=") for a in sys.argv[1:]):sys.argv.extend(["--input",os.getenv("CORPUS_JSON_DIR",str(root/"data/parsed_json"))])
    if not any(a=="--output" or a.startswith("--output=") for a in sys.argv[1:]):sys.argv.extend(["--output",os.getenv("EXTRACTION_OUTPUT_DIR",str(root/"outputs/reextraction"))])
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    runpy.run_path(str(Path(__file__).with_name("strict_runner.py")),run_name="__main__")
