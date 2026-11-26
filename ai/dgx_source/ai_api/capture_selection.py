"""Route verified capture observations into proposals, never production decisions."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from ai_api.duplicate_groups import dump

ROOT=Path(__file__).resolve().parents[1]
ALLOWED=dict(coverage={'충족','일부만 보임','식별 어려움','범위 미정/판단 보류'},
             readability={'판독 가능','판독 어려움','판단 보류'},
             lighting={'필요 표면 확인 가능','일부 가림','대부분 가림','판단 보류'},
             visibility224={'둘 다 보임','원본에만 보임','원본에서도 불확실','결함 흔적 관찰되지 않음','판단 보류'})


def route(observation, scope):
    if not observation:return 'NEEDS_REVIEW'
    if not scope or scope.get('type') not in ('door_outer_face','specified_region') or not scope.get('description','').strip():return 'HOLD_SCOPE_UNDEFINED'
    if observation['coverage']=='식별 어려움' or observation['readability']=='판독 어려움' or observation['lighting']=='대부분 가림':return 'HOLD_CAPTURE_UNSUITABLE'
    if observation['coverage']=='일부만 보임' and observation['readability']=='판독 가능':return 'SUPPLEMENTARY_PARTIAL_VIEW'
    if observation['coverage']=='충족' and observation['readability']=='판독 가능' and observation['lighting']=='필요 표면 확인 가능':
        if observation['visibility224']=='원본에만 보임':return 'HOLD_MODEL_INPUT_VISIBILITY'
        if observation['visibility224'] in ('둘 다 보임','결함 흔적 관찰되지 않음'):return 'PRIMARY_CAPTURE_CANDIDATE'
    return 'HOLD_UNCERTAIN'


def import_review(path):
    review=json.loads(path.read_text())
    if review['schema']!='door-capture-supplement-v1' or review['applied'] is not False:raise ValueError('Unexpected review')
    source=Path(review['source'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=review['sourceSHA256']:raise ValueError('Source changed')
    manifest=json.loads(source.read_text());samples={c['id']:c for c in manifest['candidates']}
    cases=review['cases'];observations=review['observations']
    if len(cases)!=16 or len({c['id'] for c in cases})!=16 or set(observations)!={c['id'] for c in cases}:raise ValueError('Incomplete review')
    prior=Path(review['priorReview'])
    if hashlib.sha256(prior.read_bytes()).hexdigest()!=review['priorReviewSHA256']:raise ValueError('Prior review changed')
    previous=json.loads(prior.read_text())['state']['cases']
    if not review.get('reviewer','').strip():raise ValueError('Missing reviewer')
    records=[]
    for c in cases:
        expected=samples[c['id']];p=Path(expected['imagePath'])
        if c['imagePath']!=str(p) or c['imageSHA256']!=expected['imageSha256'] or hashlib.sha256(p.read_bytes()).hexdigest()!=c['imageSHA256']:raise ValueError('Image changed')
        if c['prior']!=previous[c['id']]:raise ValueError('Prior observation changed')
        r=observations[c['id']]
        if any(not isinstance(r.get(k),str) or not r[k].strip() for k in ['coverage','readability','lighting','visibility224','notes']):raise ValueError('Missing observation')
        if any(r[k] not in values for k,values in ALLOWED.items()):raise ValueError('Unknown observation value')
        records.append(dict(**c,observation=r,selectionProposal=route(r,review.get('inspectionScope'))))
    out=ROOT/'ai_api/verification'/('capture_selection_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir()
    dump(out/'original_export.json',review);dump(out/'selection_proposals.json',records)
    dump(out/'summary.json',dict(status='proposals_only',sourceExport=str(path),sourceExportSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),counts=dict(Counter(r['selectionProposal'] for r in records)),inspectionScope=review.get('inspectionScope'),labelsChanged=False,manifestsChanged=False,finalTestUsed=False,trainingStarted=False,limitations='Capture suitability is not component quality or model accuracy; partial references are not evidence of whole-part GOOD'))
    print(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);args=parser.parse_args();import_review(args.review.resolve())


if __name__=='__main__':main()
