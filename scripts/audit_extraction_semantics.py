"""Run advisory lexical triage; no semantic accuracy claim."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src/extraction"))
from semantic_triage import audit, alias_key

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    for source in sorted(args.input.glob("*.json")):
        if source.name.startswith("_"):continue
        result=audit(json.loads(source.read_text(encoding="utf-8")))
        (args.output/source.name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(source.name,len(result["issues"]))

if __name__=="__main__":main()
