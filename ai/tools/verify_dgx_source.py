"""Verify public DGX source hashes and syntax without importing model code."""
import ast
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]/"dgx_source"
manifest=json.loads((root/"source_manifest.json").read_text(encoding="utf-8"))
python_count=0
for item in manifest["files"]:
    path=root/item["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item["publishedSHA256"]:
        raise SystemExit("Source hash mismatch: "+item["path"])
    if path.suffix==".py":
        ast.parse(path.read_text(encoding="utf-8"),filename=item["path"])
        python_count+=1
print(f"Verified {len(manifest['files'])} source files; {python_count} Python files parsed; no model loaded.")
