"""Read versioned imported judgments without replacing earlier review batches."""
import hashlib
import json
from pathlib import Path
from ai_api.import_door_remaining_review import validate


def load_imports(summary_paths):
    judgments={};hashes={}
    for item in summary_paths:
        path=Path(item)
        summary=json.loads(path.read_text())
        if summary.get('originalsModified') is not False or summary.get('splitApplied') is not False:raise ValueError('Review import modified original data')
        queue_path=Path(summary['queueSource'])
        review_path=path.parent/'original_user_export.json'
        if not review_path.exists():raise ValueError('Preserved review export missing')
        for source,want in [(queue_path,summary['queueSHA256']),(review_path,summary['sourceReviewSHA256'])]:
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            if digest!=want:raise ValueError('Review history source changed')
            hashes[str(source)]=digest
        review=json.loads(review_path.read_text());queue=json.loads(queue_path.read_text())
        records=validate(review,queue,summary['queueSHA256'])
        if len(records)!=summary['recordCount']:raise ValueError('Import count mismatch')
        for row in records:
            judgments[(row['validation_image'],row['train_image'])]={'decision':row['decision'],'reason':row['reason']}
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    return judgments,hashes
