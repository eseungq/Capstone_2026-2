"""Validate human framing records and prepare a descriptive 16-image GPU run."""
import argparse
import hashlib
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from ai_api.diagnostics import ROOT,RUN,read,normalize_predictions
from ai_api.verify_gpu import dump


def verify_review(manifest,review):
    if review.get('schema')!='door-framing-review-v1' or review['focusedSourceSha256']!=manifest['focusedSourceSha256']:
        raise ValueError('Framing source mismatch')
    if review['candidateHashes']!=[c['imageSha256'] for c in manifest['candidates']]:raise ValueError('Candidate hashes mismatch')
    expected={c['id'] for c in manifest['candidates']}
    if set(review['state']['cases'])!=expected:raise ValueError('Incomplete candidate set')
    for case in review['state']['cases'].values():
        if case.get('framing') not in ('전체','부분','과도한 근접','판단 불가'):raise ValueError('Unreviewed framing')
        if case.get('doorIdentity') not in ('가능','어려움','판단 불가') or case.get('angle') not in ('허용','과도한 사선','판단 불가'):
            raise ValueError('Incomplete identity/angle')


def load_frame_selection(selection,rows):
    for field in ('sourceManifest','humanReview'):
        p=Path(selection[field]).resolve()
        if not p.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Selection evidence outside workspace')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=selection[field+'Sha256']:raise ValueError('Framing evidence changed')
    manifest=json.loads(Path(selection['sourceManifest']).read_text());review=json.loads(Path(selection['humanReview']).read_text())
    verify_review(manifest,review)
    excluded={r['imagePath'] for r in manifest['previous']};lookup={r['image_path']:r for r in rows}
    requested=selection['samples'];candidates={c['imagePath']:c for c in manifest['candidates']}
    if len(requested)!=16 or {r['image_path'] for r in requested}!=set(candidates):raise ValueError('Expected 16 framing candidates')
    if Counter(r['kind'] for r in requested)!=dict(TP=4,TN=4,FP=4,FN=4):raise ValueError('Unexpected diagnostic strata')
    for row in requested:
        path=row['image_path'];c=candidates[path]
        if path in excluded or lookup.get(path)!=row:raise ValueError('Prediction changed or reviewed-image overlap')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=c['imageSha256']:raise ValueError('Image changed')
        if selection['frames'][path]!=review['state']['cases'][c['id']]:raise ValueError('Framing assignment changed')
    return requested


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--review',type=Path,required=True);args=parser.parse_args()
    manifest=json.loads(args.source.read_text());review=json.loads(args.review.read_text());verify_review(manifest,review)
    output=ROOT/'ai_api/verification'/('frame_run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    archived=output/'human_framing_original.json';archived.write_bytes(args.review.read_bytes())
    rows=normalize_predictions(read(RUN/'best_internal_validation_predictions.csv'));lookup={r['image_path']:r for r in rows}
    samples=[lookup[c['imagePath']] for c in manifest['candidates']]
    frames={c['imagePath']:review['state']['cases'][c['id']] for c in manifest['candidates']}
    selection=dict(schema='door-framing-diagnostic-v1',sourceManifest=str(args.source.resolve()),sourceManifestSha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                   humanReview=str(archived),humanReviewSha256=hashlib.sha256(archived.read_bytes()).hexdigest(),samples=samples,frames=frames,
                   finalTestUsed=False,design='descriptive only; framing and confusion type are confounded, not causal comparison')
    load_frame_selection(selection,rows);selected_path=output/'selection.json';dump(selected_path,selection)
    cross=defaultdict(Counter)
    for row in samples:cross[row['kind']][frames[row['image_path']]['framing']]+=1
    dump(output/'review_summary.json',dict(framingCounts=dict(Counter(v['framing'] for v in frames.values())),confusionByFraming={k:dict(v) for k,v in cross.items()},
        focusObservation=review['state']['focus'],sourceReviewSha256=hashlib.sha256(archived.read_bytes()).hexdigest(),causalAttribution=False,modelChanged=False))
    script=("#!/usr/bin/env bash\nset -Eeuo pipefail\ncd /path/to/private/validated-project\n"
        "export DOOR_API_MODEL_VERSION='UNREGISTERED-door-swin-tiny-diagnostic'\nexport DOOR_API_DEVELOPMENT_CONTRACT=1\nexport DOOR_DOCKER_SUDO=\"${DOOR_DOCKER_SUDO:-1}\"\n"
        "export DOOR_API_REUSE_HTTP_REPORT='/path/to/private/validated-project/ai_api/verification/20261016T135431_704517Z/verification.json'\n"
        f"export DOOR_API_SELECTION_FILE='{selected_path}'\nbash ai_api/run_gpu.sh diagnose\n")
    (output/'run.sh').write_text(script)
    print('[FRAMING SUMMARY]',output/'review_summary.json');print('[FRAMING GPU RUN]',output/'run.sh')


if __name__=='__main__':main()
