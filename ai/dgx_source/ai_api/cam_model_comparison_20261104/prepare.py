"""Freeze the three reviewed photos held out by both image-level validation lists."""
import ast, csv, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/path/to/private/validated-project')
OLD_SOURCE=Path('/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009/train_door_swin.py')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def table(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def dataset_node(path):
    tree=ast.parse(path.read_text())
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    return next(n for n in main.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset')

def main():
    code=ROOT/'ai_api/cam_model_comparison_20261104'
    reviews=Path(json.loads((ROOT/'ai_api/cam_followup_20261104/latest_review.json').read_text())['directory'])
    planned=json.loads((reviews/'old_new_comparison_plan.json').read_text())
    previous=Path(json.loads((ROOT/'ai_api/cam_followup_20261104/latest.json').read_text())['output'])
    previous_selection=json.loads((previous/'selection.json').read_text())
    previous_report=json.loads((previous/'report.json').read_text())
    previous_rows={r['id']:r for r in previous_report['samples']}
    candidate=json.loads((ROOT/'ai_api/door_e02_candidate.json').read_text())
    oldrun=Path(planned['oldModel']['run']);newrun=ROOT/candidate['run']
    oldcfg=json.loads((oldrun/'run_config.json').read_text());newcfg=json.loads((newrun/'run_config.json').read_text())
    assert oldcfg['versions']==newcfg['versions']
    assert oldcfg['normalization']==newcfg['normalization']
    assert oldcfg['class_mapping']==newcfg['class_mapping']=={'양품':0,'불량품':1}
    assert oldcfg['config']['model_name']==newcfg['config']['model_name']=='swin_tiny_patch4_window7_224.ms_in1k'
    assert oldcfg['config']['image_size']==newcfg['config']['image_size']==224
    assert oldcfg['config']['prediction_cutoff']==newcfg['config']['prediction_cutoff']==.5
    old_verified=json.loads((ROOT/'outputs/evaluation/door_20261015_024950_271668/evaluation_config.json').read_text())
    assert sha(OLD_SOURCE)==old_verified['training_source_sha256']
    new_source=ROOT/candidate['trainingSource']
    assert sha(new_source)==candidate['trainingSourceSHA256']
    old_ast=ast.dump(dataset_node(OLD_SOURCE),include_attributes=False)
    assert old_ast==ast.dump(dataset_node(new_source),include_attributes=False)
    expected_old=planned['oldModel']['checkpointSHA256'];expected_new=candidate['checkpointSHA256']
    assert sha(oldrun/'best.pt')==old_verified['model_sha256']==expected_old
    assert sha(newrun/'best.pt')==expected_new
    roles={}
    for role in ('train','internal_validation'):
        info=oldcfg['manifests'][role];path=Path(info['path']);assert sha(path)==info['sha256']
        for row in table(path):
            assert row['image_path'] not in roles
            roles[row['image_path']]=role
    new_selection_path=newrun/'model_selection_used.csv'
    assert sha(new_selection_path)==previous_selection['manifestSHA256']
    new_selection={r['image_path']:r for r in table(new_selection_path)}
    old_prediction_path=oldrun/'best_internal_validation_predictions.csv'
    old_predictions={r['image_path']:r for r in table(old_prediction_path)}
    human={r['id']:r for r in json.loads((reviews/'raw_review.json').read_text())['cases']}
    assert [r['id'] for r in planned['cases']]==['followup_01','followup_08','followup_12']
    out=ROOT/'outputs/door_e02_live/cam_model_comparison_20261104'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out.mkdir(parents=True,exist_ok=False)
    copied_source=out/'frozen_dataset_source.py'
    shutil.copyfile(OLD_SOURCE,copied_source)
    assert sha(copied_source)==sha(OLD_SOURCE)
    samples=[]
    for sample in planned['cases']:
        sid=sample['id'];path=Path(sample['image_path'])
        assert sha(path)==sample['imageSHA256']
        assert roles[str(path)]=='internal_validation' and str(path) in new_selection
        assert human[sid]['visibility']=='224에서도 확인 가능'
        target=out/sid;target.mkdir()
        for name in ('original.jpg','input224.png'):shutil.copyfile(previous/sid/name,target/name)
        old=old_predictions[str(path)];reference=previous_rows[sid]
        assert old['class_id']==new_selection[str(path)]['class_id']=='1'
        samples.append(dict(sample,oldSavedGPUBatchScore=float(old['raw_defect_score']),newCPUReference=reference,newCPURawReference=str(previous/sid/'current_raw.npy'),newCPURawReferenceSHA256=sha(previous/sid/'current_raw.npy'),previousHumanReview=human[sid],oldRole='internal_validation',newRole='model_selection'))
    frozen=dict(schema='old20-new2-fixed-cam-comparison-v1',output=str(out),purpose='same-photo same-layer explanation diagnostic; not independent model performance selection',modelName=oldcfg['config']['model_name'],versions=oldcfg['versions'],normalization=oldcfg['normalization'],modelHashes=dict(old=expected_old,new=expected_new),modelRuns=dict(old=str(oldrun),new=str(newrun)),configHashes=dict(old=sha(oldrun/'run_config.json'),new=sha(newrun/'run_config.json')),epochs=dict(old=20,new=2),modelVersions=dict(old='door-swin-tiny-e20-8d042c7bfab2',new=candidate['modelVersion']),layer='layers.3.blocks.1.norm1',target='DEFECT logit',datasetSource=str(copied_source),datasetOriginalSource=str(OLD_SOURCE),datasetSourceSHA256=sha(OLD_SOURCE),datasetASTSHA256=hashlib.sha256(old_ast.encode()).hexdigest(),reviewSHA256=sha(reviews/'raw_review.json'),samples=samples,sourceCodeHashes={name:sha(code/name) for name in ('run.py','launch.py','run.sh')},newTrainingPerformed=False,productionChanged=False,finalTestImagesRead=False,calibrationOrPolicyImagesRead=False,independentPerformanceEvaluation=False)
    paths=[copied_source,oldrun,newrun]+[Path(r[k]) for r in samples for k in ('image_path','newCPURawReference')]
    assert all(path.is_relative_to(ROOT) for path in paths), 'all runtime reads must be inside the mounted project'
    (out/'comparison_manifest.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    (code/'latest.json').write_text(json.dumps(dict(output=str(out),manifestSHA256=sha(out/'comparison_manifest.json')),indent=2)+'\n')
    print('COMPARISON_PREPARED',out,flush=True)
    print('SOURCE_PHOTOS',[(r['id'],r['oldRole'],r['newRole']) for r in samples],flush=True)

if __name__=='__main__':main()
