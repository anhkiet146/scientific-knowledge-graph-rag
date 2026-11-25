"""Observed metadata for new runs; never reconstruct historical settings."""
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import hashlib
import json
import os
from pathlib import Path
import platform


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_metadata():
    packages = {}
    for name in ("numpy", "sentence-transformers", "neo4j", "google-genai", "openai"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "os": platform.platform(),
        "processor": platform.processor() or None,
        "logical_cpus": os.cpu_count(), "packages": packages,
        "scope": "observed_current_run_only",
        "neo4j_server_version": None, "grobid_server_version": None,
        "gpu_used": None,
    }


def save_run_metadata(path, *, question_file, corpus_dir, config, index_preparation):
    manifest = {
        "runtime": runtime_metadata(), "configuration": config,
        "question_file_sha256": file_sha256(question_file),
        "corpus_files": [{"name": p.name, "sha256": file_sha256(p)}
                         for p in sorted(Path(corpus_dir).glob("*.json"))],
        "index_preparation": index_preparation,
        "timing_scope": {
            "query_latency_excludes": ["corpus_loading", "index_preparation", "cached_translation"],
            "kg_request": "backend request through answer; separately logged stages",
            "passage_request": "local retrieval plus answer generation",
            "cross_system_end_to_end_equivalence": False,
        },
        "qa_scoring_method": "llm_rubric_ragas_informed",
        "independent_gold": False, "held_out_questions": False,
    }
    path = Path(path)
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        for field in ("configuration", "question_file_sha256", "corpus_files"):
            if previous[field] != manifest[field]:
                raise ValueError(f"Run provenance changed: {field}; use a new output directory")
        previous.setdefault("continuations", []).append({
            "runtime": manifest["runtime"], "index_preparation": index_preparation})
        manifest = previous
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
