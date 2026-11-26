"""Validate human input/region annotations and freeze equal-area 224 masks; no inference."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
from frame_model.check import ROOT
from frame_model.train import dump
from ai_api.focused_cam import roi_to_input,matched_control


def validate(payload,source):
    if payload.get('schema')!=source['schema'] or payload.get('reviewId')!=source['reviewId']:raise ValueError('Review/source mismatch')
    if payload.get('probePlanSha256')!=source['probePlanSha256']:raise ValueError('Probe source mismatch')
    if not payload.get('reviewer','').strip():raise ValueError('Reviewer missing')
    expected={c['id'] for c in source['cases']}
    if set(payload.get('cases',{}))!=expected:raise ValueError('Photo IDs differ')
    cases=[]
    for item in source['cases']:
        r=payload['cases'][item['id']]
        if any(r.get(k) not in ['clear','weak','unknown'] for k in ['visibility224','visibility448']):raise ValueError('Visibility missing: '+item['id'])
        if r.get('regionStatus')=='unavailable':
            if not r.get('note','').strip():raise ValueError('Reason required: '+item['id'])
            cases.append({'id':item['id'],'status':'unavailable','reason':r['note'],'visibility224':r['visibility224'],'visibility448':r['visibility448']});continue
        if r.get('regionStatus')!='marked':raise ValueError('Region unfinished: '+item['id'])
        rect,valid=roi_to_input(r.get('partBox',[]),item['displaySize']);background=matched_control(rect,valid,r.get('backgroundCenter',[]))
        area=(rect[2]-rect[0])*(rect[3]-rect[1]);other_area=(background[2]-background[0])*(background[3]-background[1])
        if area<=0 or area!=other_area:raise ValueError('Mask area differs')
        cases.append({'id':item['id'],'status':'marked','part_mask_224':list(rect),'background_mask_224':list(background),'display_crop_224':list(valid),'equal_area_pixels':area,'visibility224':r['visibility224'],'visibility448':r['visibility448'],'note':r.get('note','')})
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('review',type=Path);args=parser.parse_args()
    payload=json.loads(args.review.read_text());directory=(ROOT/'outputs/frame_input_background'/payload['reviewId']).resolve()
    if directory.parent!=(ROOT/'outputs/frame_input_background').resolve():raise ValueError('Invalid review path')
    source=json.loads((directory/'source.json').read_text());cases=validate(payload,source)
    if hashlib.sha256(Path(source['probePlan']).read_bytes()).hexdigest()!=source['probePlanSha256']:raise ValueError('Probe source changed')
    for item in source['cases']:
        for asset,sha in item['asset_sha256'].items():
            if hashlib.sha256((directory/asset).read_bytes()).hexdigest()!=sha:raise ValueError('Input asset changed')
    out=ROOT/'outputs/frame_input_background_validation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    shutil.copyfile(args.review,out/'human_review_original.json');dump(out/'validated_regions.json',{'schema':'frame_validated_background_masks_v1','reviewId':payload['reviewId'],'source':str(directory/'source.json'),'source_sha256':hashlib.sha256((directory/'source.json').read_bytes()).hexdigest(),'review_sha256':hashlib.sha256(args.review.read_bytes()).hexdigest(),'cases':cases,'training_performed':False,'inference_performed':False,'no_semantic_ground_truth_certification':True})
    dump(ROOT/'frame_model/latest_input_background_validation.json',{'directory':str(out),'regions':str(out/'validated_regions.json')})
    print('[INPUT/BACKGROUND VALIDATED]',out/'validated_regions.json')

if __name__=='__main__':main()
