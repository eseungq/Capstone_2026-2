"""Optional startup smoke check using ONE internal-validation photo; never final test data."""
import csv
import json
import math
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path('/path/to/private/validated-project')


def check(base,service):
    print('[연결 점검 시작] 내부 검증 사진 1장 / 실제 HTTP 업로드→GPU 추론→판단 보류 저장→재조회',flush=True)
    with (ROOT/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig',newline='') as f:
        sample=next(csv.DictReader(f))
    with (ROOT/'outputs/evaluation/door_20261015_024950_271668/predictions.csv').open(encoding='utf-8-sig',newline='') as f:
        baseline=next(r for r in csv.DictReader(f) if r['image_path']==sample['image_path'])
    def request(path,data=None,raw=False):
        headers={'X-Door-Token':service.token}
        if data is not None:
            headers['Content-Type']='application/octet-stream' if raw else 'application/json'
            # Deliberately unrelated to labels and input filesystem names.
            if raw: headers['X-File-Name']='connection_check.jpg'
            else: data=json.dumps(data).encode()
        with urlopen(Request(base+path,data=data,headers=headers),timeout=300) as response: return json.load(response)
    item=request('/api/uploads',Path(sample['image_path']).read_bytes(),True)
    ident=item['id'];prediction=request(f'/api/records/{ident}/inspect',{})['prediction']
    assert prediction['predicted_class']==int(baseline['predicted_class']),'Class differs from validated result'
    delta=abs(prediction['raw_defect_score']-float(baseline['raw_defect_score']))
    assert math.isfinite(delta) and math.isclose(prediction['raw_defect_score'],float(baseline['raw_defect_score']),abs_tol=1e-6,rel_tol=1e-4),f'Score difference too large: {delta}'
    # HTTP save path, explicitly identified as an automated check, not a human judgment.
    item=request(f'/api/records/{ident}/review',dict(judgment='판단 보류',note='[자동 연결 점검] 실제 작업자 판정이 아닙니다.',actor='self_check'))
    again=request(f'/api/records/{ident}')
    assert again['prediction']==prediction and again['review']['judgment']=='판단 보류'
    assert any(r['id']==ident for r in request('/api/records')['items'])
    from app import Store
    reopened=Store(service.store.root).get(ident)
    assert reopened['prediction']==prediction and reopened['review']==again['review']
    evidence=dict(status='complete',inspection_id=ident,image_path=sample['image_path'],
        scope='one internal-validation image; real GPU; no final test data',
        upload_inspect_review_reload=True,sqlite_reopened=True,model_class_matches=True,
        baseline_defect_score=float(baseline['raw_defect_score']),new_defect_score=prediction['raw_defect_score'],
        absolute_score_difference=delta,score_tolerance=dict(absolute=1e-6,relative=1e-4),
        batch_note='service batch=1 vs validation batch=8; small floating-point differences possible',processing_ms=prediction['processing_ms'])
    try:
        cam=request(f'/api/records/{ident}/cam',dict(target_class=prediction['predicted_class']))
        evidence['gradcam']=dict(status='complete',target_class=cam['target_class'],constant=cam['constant'])
    except Exception as e:
        evidence['gradcam']=dict(status='failed',error=str(e))
        print('[Grad-CAM 점검 실패] 기본 추론/저장 결과는 보존: '+str(e),flush=True)
    dest=service.store.root/f'self_check_{ident}.json';dest.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print('[연결 점검 완료] '+json.dumps(evidence,ensure_ascii=False),flush=True)
    print('[점검 기록] '+str(dest),flush=True)
