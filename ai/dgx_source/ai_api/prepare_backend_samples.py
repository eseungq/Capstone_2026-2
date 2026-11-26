"""Package preserved real DOOR HTTP examples and inactive payload drafts; no inference/network."""
import base64
import hashlib
import io
import json
import math
import shutil
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image
from ai_api.duplicate_groups import ROOT


def load(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    restart=ROOT/'ai_api/verification/integration_20261027T182324_087150Z';legacy=ROOT/'ai_api/verification/20261027T182324_087580Z';backend=ROOT/'outputs/backend_alignment_20261028/source_057ab0c'
    report=load(restart/'integration.json');assert report['freshGpuExecuted'] and report['freshHttpExecuted']
    out=ROOT/'outputs/backend_alignment_20261028'/('exchange_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));(out/'actual_preserved').mkdir(parents=True);(out/'inactive_payload_drafts').mkdir();(out/'decoded_png').mkdir()
    selection=[('good',restart/'restart-1-good_response.json',False),('defect_nonzero',restart/'restart-1-defect_response.json',False),('defect_zero',legacy/'sample_3_response.json',False),('cam_failure_injected',legacy/'injected_cam_response.json',True),('image_access_error',legacy/'image_missing_response.json',False),('corrupt_image_error',legacy/'broken_image_response.json',False),('model_version_error',legacy/'wrong_version_response.json',False)]
    checks=[];sources={}
    for name,path,injected in selection:
        raw=load(path);saved=out/'actual_preserved'/(name+'_response.json');shutil.copyfile(path,saved);sources[str(path)]=sha(path);assert sha(path)==sha(saved)
        request=path.with_name(path.name.replace('_response.json','_request.json'))
        if request.exists():shutil.copyfile(request,out/'actual_preserved'/(name+'_request.json'));sources[str(request)]=sha(request)
        entry=dict(case=name,source=str(path),sourceSHA256=sha(path),failureInjected=injected,newInferenceExecuted=False,newHttpExecuted=False)
        if 'error' in raw:
            entry.update(errorShape='current_development_not_final_backend_example',missingBackendExampleErrorFields=[k for k in ('message','traceId','inspectionId') if k not in raw['error']]);checks.append(entry);continue
        score=raw['rawDefectProbability'];assert math.isfinite(score) and 0<=score<=1 and (raw['predictedQuality']=='DEFECT')==(score>=.5)
        assert raw['calibratedDefectProbability'] is None and raw['calibratorVersion'] is None
        entry.update(calibrationNullVerified=True,classificationConsistent=True,modelVersion=raw['modelVersion'],classificationTimeMs=raw['inferenceTimeMs'],backendIntegerTimeFieldNeedsAgreement=not isinstance(raw['inferenceTimeMs'],int))
        candidate=dict(raw);state=raw['gradcam']['status'];issues=['inferenceTimeMs remains the original classification-only floating value; do not treat this draft as contract-compliant; fresh total-duration measurement and integer representation agreement required']
        if state=='NOT_GENERATED_GOOD':candidate['gradcam']=None
        elif state=='FAILED':candidate['gradcam']=None
        elif state=='GENERATED':
            encoded=raw['gradcam']['base64'];png=base64.b64decode(encoded,validate=True)
            with Image.open(io.BytesIO(png)) as image:
                assert image.format=='PNG' and image.size==(raw['imageWidth'],raw['imageHeight']);image.verify()
            (out/'decoded_png'/(name+'.png')).write_bytes(png)
            entry.update(decodedPngBytes=len(png),pngSize=[raw['imageWidth'],raw['imageHeight']],base64Chars=len(encoded),currentPayloadWouldMissBackendCamFields=True)
            candidate['gradcam']=dict(targetClass='DEFECT',format='png',imageBase64=encoded)
        else:
            candidate=None;issues.append('Zero/constant map semantics pending; do not map successful computation to backend FAILED or silently fabricate CAM')
        dump(out/'inactive_payload_drafts'/(name+'.json'),dict(activated=False,actualBackendValidated=False,payloadFieldsOnlyCandidate=candidate,originalCamState=state,unresolved=issues))
        entry['camComputationState']=state;checks.append(entry)
    source_document=Path('/path/to/private-user/다운로드/Telegram Desktop/AI연동_전달_DOOR_1028.md');shutil.copyfile(source_document,out/'backend_handoff_original.md');sources[str(source_document)]=sha(source_document)
    files={str(p.relative_to(backend)):sha(p) for p in backend.rglob('*') if p.is_file()}
    result=dict(scope='offline source comparison and preserved real-response exchange; not live backend validation',backendRepository='eseungq/Capstone_2026-2',backendCommit='057ab0cd17feaeeccc4250640a9ed970a187243d',sourceHashes=sources,backendSnapshotHashes=files,checks=checks,modelVersionUsedInActualEvidence=report['modelVersion'],modelVersionProposal='door-swin-tiny-e20-8d042c7bfab2',modelVersionProposalRegistered=False,currentServiceModified=False,backendOrDBModified=False,newGpuExecuted=False,newHttpExecuted=False,finalV4Compliance=False,finalTestUsed=False)
    dump(out/'exchange_manifest.json',result)
    (out/'README.md').write_text('''# 승규님 응답 샘플 교환용 자료\n\nactual_preserved/: 이전 실제 GPU·HTTP 검증 응답과 요청의 원문 사본. 모델 버전·검사 ID·시간을 바꾸지 않았다. 과거 localhost URL은 종료된 시험 서버이므로 현재 접근 주소가 아니다. injected 표시는 시험 전용 오류 주입이며 실제 모델 성능 사례가 아니다.\n\ninactive_payload_drafts/: 백엔드에서 요구하는 gradcam 필드만 맞춘 비활성 제안. 새로운 GPU/HTTP 실행 결과나 완성된 계약 응답이 아니다. 처리 시간은 과거 분류 시간 그대로라 다운로드~CAM 시간 계약에 맞지 않는다. 0맵은 임의 변환하지 않았다.\n\ndecoded_png/: 원래 base64를 PNG로 복원해 형식·표시 크기를 확인한 파일. DEFECT 예측 사례의 원래 정답은 GOOD인 FP이며 실제 불량 정답 사례로 소개하지 않는다.\n\nexchange_manifest.json: 원본 해시·실제 모델 식별자·검증 범위·주입 여부·미확정 사항.\n\n새 모델 버전 제안 door-swin-tiny-e20-8d042c7bfab2는 등록·실행되지 않았다. 샘플 원문의 UNREGISTERED-door-swin-tiny-diagnostic을 몰래 바꾸지 않았다. 등록 후 서버와 백엔드를 같은 버전으로 설정하고 새 실제 응답을 받아야 한다.\n\n백엔드 담당자는 실제 Java/Jackson 검증에 이 자료를 입력해 결과를 회신할 수 있다. 여기서는 Java/DB 실행을 하지 않았다. 원천 사진·가중치·실행 DB·비밀값은 이 자료에 포함하지 않았다. 패킷에 큰 PNG/base64가 있으므로 GitHub가 아니라 팀의 적절한 파일 전달 경로를 사용한다.\n''')
    dump(ROOT/'outputs/backend_alignment_20261028/latest_exchange.json',dict(output=str(out),manifest=str(out/'exchange_manifest.json'),readme=str(out/'README.md')))
    print(json.dumps(dict(output=str(out),cases=len(checks),newGpuExecuted=False,newHttpExecuted=False),ensure_ascii=False))

if __name__=='__main__':main()
