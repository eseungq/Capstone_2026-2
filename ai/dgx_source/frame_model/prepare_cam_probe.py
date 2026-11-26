"""Freeze a small no-training probe and record observations, not confirmed causes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageOps
from frame_model.check import ROOT
from frame_model.train import dump,write_csv


def main():
    review=ROOT/'outputs/frame_cam_review/20261026T173009_535686Z'
    selection=json.loads((review/'selection.json').read_text());cam=json.loads((review/'cam_report.json').read_text())
    human_dir=Path(json.loads((ROOT/'frame_model/latest_cam_layer_summary.json').read_text())['directory']);human=json.loads((human_dir/'summary.json').read_text())
    if not human['complete'] or human['review_id']!=selection['review_id']:raise ValueError('Complete matching layer review required')
    out=ROOT/'outputs/frame_cam_diagnosis'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    items=[];measurements=[]
    for item in selection['items']:
        if item['pair']['defect_type'] not in ['헤밍 불량','홀 변형']:continue
        ident=item['id'];label=json.loads((review/ident/'label.json').read_text(encoding='utf-8-sig'));declared=label['images'][0]
        with Image.open(review/ident/'display.png') as im: contained=ImageOps.contain(im,(224,224),method=Image.Resampling.BICUBIC).size
        for annotation in label['annotations']:
            box=annotation['bbox']
            measurements.append({'id':ident,'type':item['pair']['defect_type'],'source_class':item['pair']['actual'],'display_width':item['display_size'][0],'display_height':item['display_size'][1],'contained_width':contained[0],'contained_height':contained[1],'padding_area_fraction':1-contained[0]*contained[1]/224**2,'annotation_bbox_width_proxy_224':box[2]/declared['width']*contained[0],'annotation_bbox_height_proxy_224':box[3]/declared['height']*contained[1],'bbox_interpretation':'scale proxy only; label coordinates/extent not verified as precise defect mask'})
        frozen={**item,'display_path':str(review/ident/'display.png'),'display_sha256':hashlib.sha256((review/ident/'display.png').read_bytes()).hexdigest(),'baseline_results':cam['samples'][ident],'baseline_root':str(review)}
        frozen['baseline_raw_sha256']={model:{layer:hashlib.sha256((review/ident/model/layer/'raw.npy').read_bytes()).hexdigest() for layer in selection['layers']} for model in ['unified',item['specialist_id']]}
        items.append(frozen)
    checkpoints={k:v for k,v in selection['checkpoints'].items() if k in ['unified','type_03','type_04']}
    plan={'schema':'frame_cam_objective_probe_v1','status':'prepared_not_executed','source_selection':str(review/'selection.json'),'source_selection_sha256':hashlib.sha256((review/'selection.json').read_bytes()).hexdigest(),'source_report_sha256':hashlib.sha256((review/'cam_report.json').read_bytes()).hexdigest(),'source_human_summary':str(human_dir/'summary.json'),'source_human_summary_sha256':hashlib.sha256((human_dir/'summary.json').read_bytes()).hexdigest(),'items':items,'checkpoints':checkpoints,'layers':selection['layers'],'objectives':['defect','margin'],'interpretation':{'defect':'class1 logit: original contracted Grad-CAM target','margin':'class1 logit minus class0 logit: offline diagnostic only, never a service replacement'},'training_performed':False,'service_changed':False,'final_test_used':False,'score_tolerance':{'absolute':1e-6,'relative':1e-4},'raw_cam_reproduction_tolerance':{'absolute':1e-12,'relative':1e-6},'scope':'8 existing images, 3 frozen models, 2 candidate layers, 2 objectives; no new photos, masks, crops, thresholds, labels, calibration, or weight updates'}
    dump(out/'probe_plan.json',plan);write_csv(out/'input_geometry.csv',measurements)
    observations={'status':'observations_not_cause_confirmation','reviewed_probe_images':8,'real_defect_images':6,'real_good_false_positives':2,'effective_input_heights':sorted({r['contained_height'] for r in measurements}),'feature_shapes':[[1,7,7,768],[1,14,14,384]],'feature_grid_nominal_input_spacing':[32,16],'feature_grid_spacing_is_not_exact_defect_coordinate_resolution':True,'no_cam_failure_or_state_change_in_source_run':all(m['state_unchanged'] for m in cam['models'].values()) and not cam['errors'],'unresolved_hypotheses':['coarse spatial representation and wide-image padding','224 input visibility limits','class1-logit explanation versus binary decision contrast','background/capture-condition shortcuts','annotation semantics and unverified exact coordinates','residual overlay/feature interpretation limitations despite successful computation']}
    dump(out/'observations.json',observations)
    dump(ROOT/'frame_model/latest_cam_probe.json',{'directory':str(out),'plan':str(out/'probe_plan.json')})
    print('[CAM PROBE PREPARED]',out/'probe_plan.json')

if __name__=='__main__':main()
