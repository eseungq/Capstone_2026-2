"""Recheck historical DOOR score evidence against current files; no GPU or test-set reads."""
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
from ai_api.verify_gpu import ROOT,RUN,dump
from prototype.engine import sha

EXPECTED='8d042c7bfab20ba2527ef3693aed08e0df7e1b1ce58acc45b44de7ae5d0d6ab7'


def main():
    out=ROOT/'outputs/door_integration_20261028'/('score_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(parents=True)
    if sha(RUN/'best.pt')!=EXPECTED:raise ValueError('DOOR checkpoint differs; do not replace it')
    internal={str(Path(r['image_path']).resolve()) for r in csv.DictReader((ROOT/'outputs/manifests/door_internal_validation.csv').read_text(encoding='utf-8-sig').splitlines())}
    predictions={str(Path(r['image_path']).resolve()):r for r in csv.DictReader((RUN/'best_internal_validation_predictions.csv').read_text(encoding='utf-8-sig').splitlines())}
    if len(internal)!=2039 or set(predictions)!=internal:raise ValueError('Internal manifest coverage differs')
    records={};sources=[];model_environments=set()
    for path in sorted((ROOT/'ai_api/verification').glob('diagnose_*/diagnostic.json')):
        report=json.loads(path.read_text())
        if not report.get('samples'):continue
        model=report['model']
        if model['model_sha256']!=EXPECTED:raise ValueError('Different model in source evidence')
        if model['classes']!={'양품':0,'불량품':1} or model['precision']!='FP32' or model['cutoff']!=.5:raise ValueError('Class/precision/cutoff differs')
        model_environments.add(json.dumps({k:model[k] for k in ['gpu','versions','precision','normalization','preprocessing']},sort_keys=True))
        sources.append({'path':str(path),'sha256':sha(path)})
        for sample in report['samples']:
            if 'singleScore' not in sample:continue
            image=Path(sample['imagePath']).resolve()
            if str(image) not in internal:raise ValueError('Non-internal image forbidden')
            current_image_sha=sha(image)
            if current_image_sha!=sample['imageSha256']:raise ValueError('Original bytes changed')
            saved=float(predictions[str(image)]['raw_defect_score'])
            if saved!=sample['savedBatch8Score']:raise ValueError('Historical saved score/reference CSV differs')
            a=sample['singleScore'];b=sample['recreatedBatch8Score']
            if not all(math.isfinite(v) and 0<=v<=1 for v in [saved,a,b]):raise ValueError('Invalid historical score')
            records[current_image_sha]={'imageSha256':current_image_sha,'imagePath':str(image),'actualClass':int(predictions[str(image)]['class_id']),'sourceReport':str(path),'savedBatch8':saved,'single':a,'recreatedBatch8':b,'singleAbsoluteDifference':abs(a-saved),'recreatedBatchAbsoluteDifference':abs(b-saved),'singleStrictMatch':math.isclose(a,saved,abs_tol=1e-6,rel_tol=1e-4),'recreatedBatchStrictMatch':math.isclose(b,saved,abs_tol=1e-6,rel_tol=1e-4),'classChanged':int(a>=.5)!=int(saved>=.5),'savedCutoffDistance':abs(saved-.5),'singleCutoffDistance':abs(a-.5),'storedInputTensorHashesEqual':bool(sample['inputTensorSha256']) and sample['inputTensorSha256']==sample['batchInputTensorSha256'],'inputEvidenceScope':'Historical tensor hashes re-read; current original bytes rehashed; tensors not recomputed in this CPU run'}
    rows=list(records.values());differences=sorted(r['singleAbsoluteDifference'] for r in rows)
    if not rows:raise ValueError('No evidence')
    report={'scope':'historical GPU evidence re-audited on CPU, not fresh inference','currentCheckpointSha256':EXPECTED,'currentOriginalByteHashesVerified':len(rows),'historicalTensorHashMatches':sum(r['storedInputTensorHashesEqual'] for r in rows),'historicalModelEnvironmentGroups':len(model_environments),'uniqueImages':len(rows),'strictTolerance':{'absolute':1e-6,'relative':1e-4},'singleAbsoluteDifference':{'max':max(differences),'mean':statistics.mean(differences),'median':statistics.median(differences),'p95_nearest_rank':differences[math.ceil(.95*len(differences))-1]},'singleStrictMismatches':sum(not r['singleStrictMatch'] for r in rows),'recreatedBatchStrictMismatches':sum(not r['recreatedBatchStrictMatch'] for r in rows),'recreatedBatchMaximumDifference':max(r['recreatedBatchAbsoluteDifference'] for r in rows),'classChanges':sum(r['classChanged'] for r in rows),'closestSavedCutoffDistance':min(r['savedCutoffDistance'] for r in rows),'rows':rows,'sources':sources,'finalTestUsed':False,'toleranceChanged':False,'oldFailureOverwritten':False,'causeAssessment':'Observed batch-size-associated numerical difference with identical stored input hashes and saved-batch reproduction. Low-level kernels/precision flags not isolated; no assertion of a model bug or guaranteed harmlessness.','comparisonRule':'Compare API to same batch1 standalone at original tolerance; compare saved batch8 to recreated identical batch8 at original tolerance. Report single-vs-saved batch8 strict mismatches separately; never relabel them passed.','fullInternalBatch1BoundaryImpact':'not_verified','followup':'fresh small-sample API and restart verification plus closest-to-0.5 internal cases; no final test'}
    dump(out/'score_audit.json',report)
    print('[SCORE EVIDENCE]',out/'score_audit.json');print(json.dumps({k:v for k,v in report.items() if k not in ['rows','sources']},ensure_ascii=False))

if __name__=='__main__':main()
