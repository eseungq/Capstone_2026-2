"""Preserve per-layer human CAM ratings; separate TP/FP and never auto-select a layer."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from frame_model.check import ROOT
from frame_model.train import dump,write_csv
from frame_model.summarize_cam_review import ALLOWED


def summarize(path):
    human=json.loads(path.read_text())
    if human.get('schema')!='frame_cam_layer_human_review_v2' or not human.get('reviewer','').strip():raise ValueError('Invalid reviewer/schema')
    directory=(ROOT/'outputs/frame_cam_review'/human['review_id']).resolve()
    if directory.parent!=(ROOT/'outputs/frame_cam_review').resolve():raise ValueError('Invalid review directory')
    selection=json.loads((directory/'selection.json').read_text());cam=json.loads((directory/'cam_report.json').read_text())
    if selection.get('review_layout')!='per_layer_v2' or cam['review_id']!=human['review_id']:raise ValueError('Selection/report mismatch')
    expected={x['id'] for x in selection['items']}
    if set(human['reviews'])-expected:raise ValueError('Unknown photos')
    rows=[];missing=[]
    for item in selection['items']:
        ident=item['id'];r=human['reviews'].get(ident,{})
        for field in ['original_visibility','input_visibility']:
            if r.get(field) not in ['clear','weak','unknown']:missing.append(f'{ident}.{field}')
        expected_models={'unified',item['specialist_id']}
        if set(r.get('models',{}))-expected_models:raise ValueError('Unexpected reviewed model')
        for model in expected_models:
            result=cam.get('samples',{}).get(ident,{}).get(model)
            if result is None:raise ValueError('Missing actual GPU result')
            ratings=r.get('models',{}).get(model,{}).get('layers',{})
            if set(ratings)-set(selection['layers']):raise ValueError('Unexpected reviewed layer')
            for layer in selection['layers']:
                rating=ratings.get(layer,{})
                for field,choices in ALLOWED.items():
                    if rating.get(field) not in choices:missing.append(f'{ident}.{model}.{layer}.{field}')
                info=next((x for x in result['layers'] if x['layer']==layer),None)
                if info is None:raise ValueError('Missing actual GPU layer result')
                rows.append({'id':ident,'type':item['pair']['defect_type'],'source_class':int(item['pair']['actual']),'saved_case':'shared_TP' if int(item['pair']['actual']) else 'shared_FP','image_id':item['source']['image_id'],'model':model,'model_role':'unified' if model=='unified' else 'specialist','layer':layer,'cam_status':info['status'],'scope':info['scope'],'actual_prediction':result['predicted_quality'],**{k:rating.get(k,'') for k in ALLOWED},'layer_note':rating.get('note',''),'photo_note':r.get('note',''),'original_visibility':r.get('original_visibility',''),'input_visibility':r.get('input_visibility','')})
    counts=[]
    for kind in sorted({r['type'] for r in rows}):
        for case in ['shared_TP','shared_FP']:
            for role in ['unified','specialist']:
                for layer in selection['layers']:
                    subset=[r for r in rows if (r['type'],r['saved_case'],r['model_role'],r['layer'])==(kind,case,role,layer)]
                    counts.append({'type':kind,'case':case,'model_role':role,'layer':layer,'n':len(subset),'usefulness':dict(Counter(r['usefulness'] for r in subset)),'relevance':dict(Counter(r['relevance'] for r in subset)),'background':dict(Counter(r['background'] for r in subset)),'cam_status':dict(Counter(r['cam_status'] for r in subset))})
    out=ROOT/'outputs/frame_cam_layer_summary'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    shutil.copyfile(path,out/'human_review_original.json');write_csv(out/'layer_reviews.csv',rows)
    report={'review_id':human['review_id'],'reviewer':human['reviewer'],'photos':len(selection['items']),'layer_reviews':len(rows),'complete':not missing,'missing_fields':missing,'counts':counts,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [path,directory/'selection.json',directory/'cam_report.json',Path(__file__)]},'operational_layer_selected':False,'limitations':['Selected shared-DEFECT cases, not overall explanation success rate.','TP/FP reported separately; useful-looking FP CAM is not proof of a defect.','One reviewer and small samples; internal validation used for development.']}
    dump(out/'summary.json',report);dump(ROOT/'frame_model/latest_cam_layer_summary.json',{'directory':str(out),'report':str(out/'summary.json')})
    return out,report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('review',type=Path);args=parser.parse_args()
    out,r=summarize(args.review);print('[LAYER REVIEW SUMMARY]',out);print('[COMPLETE]',r['complete'],'[MISSING]',len(r['missing_fields']))

if __name__=='__main__':main()
