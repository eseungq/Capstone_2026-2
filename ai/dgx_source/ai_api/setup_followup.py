"""Prepare issue-review and disjoint next diagnostic sample list. No GPU or training."""
import argparse
import hashlib
import json
import random
from datetime import datetime,timezone
from pathlib import Path
from ai_api.diagnostics import ROOT,RUN,read,normalize_predictions
from ai_api.prepare_review import build
from ai_api.verify_gpu import dump


def select_additional(rows,excluded,seed=20261017):
    rng=random.Random(seed);chosen=[]
    for kind in ('TP','TN','FP','FN'):
        candidates=sorted([r for r in rows if r['kind']==kind and r['image_path'] not in excluded],key=lambda r:r['image_path'])
        rng.shuffle(candidates)
        if len(candidates)<3:raise ValueError('Insufficient additional internal samples')
        chosen.extend(candidates[:3])
    return chosen


def load_selection(path,rows):
    selection=json.loads(path.read_text())
    if selection.get('schema')=='door-framing-diagnostic-v1':
        from ai_api.prepare_frame_run import load_frame_selection
        return load_frame_selection(selection,rows)
    previous=Path(selection['previousReport'])
    if hashlib.sha256(previous.read_bytes()).hexdigest()!=selection['previousReportSha256']:raise ValueError('Prior report changed')
    excluded={s['imagePath'] for s in json.loads(previous.read_text())['samples']}
    lookup={r['image_path']:r for r in rows};requested=selection['samples']
    if len(requested)!=12 or len({r['image_path'] for r in requested})!=12:raise ValueError('Expected 12 unique additional cases')
    from collections import Counter
    for row in requested:
        if row['image_path'] in excluded or lookup.get(row['image_path'])!=row:raise ValueError('Additional sample changed or overlaps prior review')
    if Counter(r['kind'] for r in requested)!=dict(TP=3,TN=3,FP=3,FN=3):raise ValueError('Unexpected strata')
    return requested


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous-report',type=Path,required=True)
    parser.add_argument('--human-review',type=Path,required=True);args=parser.parse_args()
    previous=args.previous_report.resolve();review=json.loads(args.human_review.read_text());report=json.loads(previous.read_text())
    if review['sourceReportSha256']!=hashlib.sha256(previous.read_bytes()).hexdigest():raise ValueError('Review provenance mismatch')
    output=ROOT/'ai_api/verification'/('followup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    subset=dict(report);subset['samples']=[dict(s,priorUserNotes=review['reviews'][s['id']].get('notes','')) for s in report['samples'] if s['id'] in ('sample_00','sample_02','sample_08')]
    # Assets remain in the original directory. The subset report sits beside them, under a unique name.
    subset_path=previous.parent/('issue_review_source_'+output.name+'.json');dump(subset_path,subset)
    workspace=build(subset_path)
    internal={r['image_path'] for r in read(ROOT/'outputs/manifests/door_internal_validation.csv')}
    rows=normalize_predictions(read(RUN/'best_internal_validation_predictions.csv'))
    eligible=[r for r in rows if r['image_path'] in internal]
    chosen=select_additional(eligible,{s['imagePath'] for s in report['samples']})
    selection=dict(previousReport=str(previous),previousReportSha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
                   seed=20261017,finalTestUsed=False,selectionBasis='saved prediction confusion strata, no selection by CAM appearance',samples=chosen)
    selection_path=output/'additional_selection.json';dump(selection_path,selection)
    assert load_selection(selection_path,rows)==chosen
    command=("#!/usr/bin/env bash\nset -Eeuo pipefail\ncd /path/to/private/validated-project\n"
             "export DOOR_API_MODEL_VERSION='UNREGISTERED-door-swin-tiny-diagnostic'\n"
             "export DOOR_API_DEVELOPMENT_CONTRACT=1\nexport DOOR_DOCKER_SUDO=1\n"
             "export DOOR_API_REUSE_HTTP_REPORT='/path/to/private/validated-project/ai_api/verification/20261016T135431_704517Z/verification.json'\n"
             f"export DOOR_API_SELECTION_FILE='{selection_path}'\nbash ai_api/run_gpu.sh diagnose\n")
    (output/'run_additional.sh').write_text(command)
    dump(output/'plan.json',dict(issueReview=str(workspace/'index.html'),additionalSelection=str(selection_path),
                                runScript=str(output/'run_additional.sh'),training=False,modelChanged=False,labelsChanged=False))
    print('[ISSUE REVIEW]',workspace/'index.html');print('[ADDITIONAL RUN]',output/'run_additional.sh')


if __name__=='__main__':main()
