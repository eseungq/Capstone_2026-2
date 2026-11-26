"""Build inactive, reproducible unified/specialist comparison proposals. No GPU or training."""
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
from collections import Counter
from frame_model.check import ROOT
from frame_model.train import manifests,dump,write_csv


def main():
    prep=Path(json.loads((ROOT/'frame_model/latest_preparation.json').read_text())['preparation'])
    config,tables=manifests(prep)
    first=ROOT/'outputs/frame_scope_summary/20261021T175938_637101Z'
    second=Path(json.loads((ROOT/'frame_model/latest_scope_summary.json').read_text())['directory'])
    summaries=[first,second];reviews={};evidence=[]
    for folder in summaries:
        summary=json.loads((folder/'summary.json').read_text())
        data=json.loads((folder/'human_review_original.json').read_text())
        selection=ROOT/'outputs/frame_scope_review'/summary['review_id']/'selection.json'
        bundle=json.loads(selection.read_text())
        for row in bundle['items']:
            sha=row['image_sha256']
            if sha in reviews:raise ValueError('Duplicate reviewed image')
            reviews[sha]={'review_id':summary['review_id'],'photo_id':row['id'],**data['reviews'][row['id']]}
        evidence.append({'summary':str(folder/'summary.json'),'summary_sha256':hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),'review':str(folder/'human_review_original.json'),'review_sha256':hashlib.sha256((folder/'human_review_original.json').read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256(selection.read_bytes()).hexdigest()})
    out=ROOT/'outputs/frame_experiment_plan'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    ledger=[];candidate={};quarantine=[]
    for role,rows in tables.items():
        candidate[role]=[]
        for row in rows:
            r=reviews.get(row['image_sha256']);reasons=[]
            if r:
                if r['decision'] in ['hold','exclude_candidate']:reasons.append('human_'+r['decision'])
                if r['label_match'] in ['unknown','suspect']:reasons.append('unresolved_source_label')
                if r['visibility224'] in ['lost','unknown']:reasons.append('unresolved_224_visibility')
                if r['coverage']=='unjudgeable':reasons.append('unjudgeable_inspection_region')
            entry={'image_id':row['image_id'],'type':row['defect_type'],'class_id':row['class_id'],'role':role,'reviewed':bool(r),'review_id':r['review_id'] if r else '', 'photo_id':r['photo_id'] if r else '', 'human_decision':r['decision'] if r else 'unreviewed','proposal':'quarantine' if reasons else 'retain_source_label_exploratory','reasons':'|'.join(reasons)}
            ledger.append(entry)
            if reasons:quarantine.append(entry)
            else:candidate[role].append(row)
    assert sum(r['reviewed'] for r in ledger)==96
    experiments=[];count_rows=[];file_hashes={}
    for directory,source in [('reference_source',tables),('comparison_candidate',candidate)]:
        target=out/directory;target.mkdir()
        for role,rows in source.items():
            path=target/f'unified_{role}.csv';write_csv(path,rows);file_hashes[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
            for index,kind in enumerate(config['inspection_types'],1):
                selected=[r for r in rows if r['defect_type']==kind]
                path=target/f'type_{index:02d}_{role}.csv';write_csv(path,selected);file_hashes[str(path.relative_to(out))]=hashlib.sha256(path.read_bytes()).hexdigest()
                for y in ['0','1']:
                    count_rows.append({'dataset':directory,'type':kind,'role':role,'class_id':y,'images':sum(r['class_id']==y for r in selected)})
                assert {r['class_id'] for r in selected}=={'0','1'}
    write_csv(out/'review_overlay.csv',ledger);write_csv(out/'quarantine_proposal.csv',quarantine);write_csv(out/'counts.csv',count_rows)
    for name,kind in [('unified',None)]+[(f'type_{i:02d}',k) for i,k in enumerate(config['inspection_types'],1)]:
        experiments.append({'id':name,'inspection_type':kind,'train_manifest':str(out/'comparison_candidate'/f'{name}_train.csv'),'model_selection_manifest':str(out/'comparison_candidate'/f'{name}_model_selection.csv'),'epochs':20,'seed':42,'pretrained':True,'precision':'FP32','batch_size':8,'status':'inactive_proposal'})
    for source in [tables,candidate]:
        assert not {r['group_id'] for r in source['train']}&{r['group_id'] for r in source['model_selection']}
        assert not {r['image_sha256'] for r in source['train']}&{r['image_sha256'] for r in source['model_selection']}
        for role in source:
            unified={r['image_id'] for r in source[role]}
            union=set()
            for kind in config['inspection_types']:
                part={r['image_id'] for r in source[role] if r['defect_type']==kind}
                assert not union & part;union.update(part)
            assert unified==union
    plan={'status':'inactive_exploratory_proposal','source_preparation':str(prep),'source_manifests':config['manifests'],'criteria_sha256':hashlib.sha256((ROOT/'frame_model/PHOTO_CRITERIA_V1.md').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'review_evidence':evidence,'human_reviewed':96,'source_counts':{k:len(v) for k,v in tables.items()},'candidate_counts':{k:len(v) for k,v in candidate.items()},'quarantine_images':len(quarantine),'quarantine_scope':'Only reviewed uncertain images; no propagation to unreviewed group mates or population. No deletion/relabeling. No new split.','experiments':experiments,'manifest_sha256':file_hashes,'reserved_roles_used_for_training_or_evaluation':False,'source_archive_pixels_read':False,'model_training_started':False,'official_final_test_used':False,'limitations':['Source labels for unreviewed photos are not verified.','No capture-condition-balanced held-out assessment yet.','Temporal grouping does not prove physical independence.','Reviewed photos were from training only.','Model-selection evaluation is not independent final performance.','Deployment compatibility, calibration, AUTO_PASS, Grad-CAM and quality targets remain unvalidated.']}
    dump(out/'plan.json',plan)
    dump(out/'validation.json',{'status':'passed','reviewed_images':96,'source_partition_preserved':True,'unified_equals_union_of_types':True,'train_selection_image_and_group_overlap':0,'class_coverage_per_type':'both','training_started':False})
    dump(ROOT/'frame_model/latest_experiment_plan.json',{'directory':str(out),'plan':str(out/'plan.json')})
    print('[EXPERIMENT PROPOSAL]',out);print(json.dumps({'source':plan['source_counts'],'candidate':plan['candidate_counts'],'quarantine':len(quarantine)},ensure_ascii=False))

if __name__=='__main__':main()
