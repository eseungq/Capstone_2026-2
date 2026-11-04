"""Verify the published runtime mirror without loading torch or model weights."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'source_manifest.json').read_text())
for item in manifest['files']:
    path=root/item['path']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['publishedSHA256']:
        raise SystemExit('Published source changed: '+item['path'])
print('Published runtime source hashes verified; no model loaded.')
