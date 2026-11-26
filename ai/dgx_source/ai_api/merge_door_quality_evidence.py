"""Join verified historic human observations by original image path, never by repeated sample IDs."""
import csv
import hashlib
import html
import json
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.duplicate_groups import ROOT,read_csv
from ai_api.prepare_experiment_draft import quality_overrides


def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    readiness=Path(load(ROOT/'outputs/door_data_readiness/latest.json')['output']);ledger=read_csv(readiness/'label_proposal_ledger.csv');by_path={r['image_path']:r for r in ledger};good={p:r for p,r in by_path.items() if r['proposed_image_class']=='0'}
    capdir=ROOT/'ai_api/verification/capture_consolidated_20261017T181937_234097Z';capture=read_csv(capdir/'all_reviewed_images.csv');old_good=Path(load(ROOT/'outputs/door_good_evidence/latest.json')['output']);flags=load(old_good/'label_observation_conflicts.json')
    observation_file=ROOT/'outputs/reviews/door_swin_tiny_20261008_183758_369671_internal_errors/observations.csv';cam_exports=sorted(Path('/path/to/private-user/다운로드').glob('cam_review_*.json'))
    sources=[readiness/'label_proposal_ledger.csv',capdir/'all_reviewed_images.csv',capdir/'decision_history.json',old_good/'label_observation_conflicts.json',observation_file,ROOT/'ai_api/verification/latest_data_proposal.json',Path(__file__).resolve()]+cam_exports
    proposal=load(ROOT/'ai_api/verification/latest_data_proposal.json')
    quality_files=[ROOT/Path(p) for p in proposal.get('qualityReviewFiles',[])]
    groups=load(ROOT/proposal['groupDirectory']/'groups.json')
    clarifications={row['imagePath']:row for row in quality_overrides(groups,quality_files).values()}
    sources+=quality_files
    hashes={str(p):sha(p) for p in sources};cam_by_path=defaultdict(list);image_hashes={};accepted_exports=[]
    for export in cam_exports:
        doc=load(export)
        if doc.get('schema')!='door-cam-human-review-v1':raise ValueError('Unknown human review schema')
        source=Path(doc['sourceReport'])
        if sha(source)!=doc['sourceReportSha256']:raise ValueError('CAM source changed')
        report=load(source)
        if report.get('finalTestUsed') is not False:raise ValueError('Unexpected dataset scope')
        cases={r['id']:r for r in report['samples']};hashes[str(source)]=sha(source)
        for ident,review in doc['reviews'].items():
            if ident not in cases:raise ValueError('Unknown review case')
            sample=cases[ident];path=sample['imagePath']
            if path not in by_path:raise ValueError('Review outside train/internal whitelist')
            if path not in image_hashes:image_hashes[path]=sha(path)
            if image_hashes[path]!=sample['imageSha256']:raise ValueError('Reviewed image changed')
            cam_by_path[path].append(dict(export=str(export),source=str(source),sourceSampleId=ident,exportedAt=doc['exportedAt'],savedKind=sample['savedKind'],observation=review))
        accepted_exports.append(str(export))
    capture_by_path={r['image_path']:r for r in capture};observations=defaultdict(list)
    for row in read_csv(observation_file):
        if row['image_path'] not in by_path:raise ValueError('Error sheet outside whitelist')
        if row.get('reviewer','').strip() and any(row.get(k,'').strip() for k in ['other_observations','original_defect_visibility','label_concern']):observations[row['image_path']].append(row)
    all_evidence=set(cam_by_path)|set(capture_by_path)|set(observations);good_evidence=sorted(set(good)&all_evidence)
    records=[]
    for path in good_evidence:
        history=sorted(cam_by_path.get(path,[]),key=lambda x:x['exportedAt']);latest={}
        for event in history:
            for key,value in event['observation'].items():
                if key!='layers':latest[key]=value
        reasons=[]
        if latest.get('labelAssessment')=='라벨 의심':reasons.append('human_label_suspicion_not_confirmed_relabel')
        if latest.get('originalVisibility')=='보임':reasons.append('human_visibility_field_needs_target_damage_interpretation')
        if any(r['image_path']==path for r in flags) and path not in clarifications:reasons.append('written_capture_damage_observation_conflicts_with_GOOD')
        if latest.get('framing') in ('부분','과도한 근접'):reasons.append('partial_view_not_whole_scope_good_certificate')
        records.append(dict(image_path=path,current_group_id=good[path]['group_id'],source_annotation_categories=good[path]['source_annotation_categories'],current_proposed_class_id=0,camReviewHistory=history,latestNonLayerObservations=latest,captureRecord=capture_by_path.get(path),errorObservations=observations.get(path,[]),reviewFlags=reasons,qualityGoodCertified=False,labelChanged=False))
    out=ROOT/'outputs/door_quality_evidence_merge'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    dump(out/'good_evidence_records.json',records);dump(out/'all_cam_review_history.json',dict(cam_by_path))
    direct_scope=[]
    for row in flags:
        path=row['image_path'];source=by_path[path]
        if sha(source['json_path'])!=source['json_sha256']:raise ValueError('Flag source label changed')
        label=load(source['json_path']);attrs=[a.get('attributes',{}) for a in label['annotations']]
        assert all(a.get('part')=='도어' and a.get('quality')=='양품' for a in attrs)
        if row['review_id']=='new_07':
            observation='원본에 도어·하단 트림·바퀴 인접 패널이 함께 보이며 경계 부근 자국이 보인다. 검사 대상 도어의 손상인지 인접 부품·오염인지 최종 확인 필요.'
        else:observation='원본 도어 표면의 가로 라인 부근에 국소 찍힘/도장 자국처럼 보이는 반응이 있다. 반사·오염과 실제 손상을 구분할 필요가 있어 확정 정답으로 변경하지 않음.'
        clarification=clarifications.get(path)
        direct_scope.append(dict(reviewId=row['review_id'],imagePath=path,sourceJSON=source['json_path'],sourceJSONSHA256=source['json_sha256'],sourceQuality='양품',sourceHasDamageAnnotation=False,priorHumanObservation=row['notes'],priorCoverage=row['source_coverage'],priorVisibility224=row['source_visibility224'],inspectionScope='door_outer_face_from_existing_capture_export',currentAIObservation=observation,newAIInspection='original_resolution_image_viewed',disposition=clarification['decision'] if clarification else 'HOLD_FROM_CONFIRMED_GOOD_UNTIL_TARGET_DAMAGE_RESOLVED',suggestedDefectCandidate=clarification['proposedClass']==1 if clarification else True,sourceLabelsModified=False,scopeResolved=bool(clarification),latestUserClarification=clarification))
    dump(out/'two_case_scope_review.json',direct_scope)
    summary=dict(status='human_evidence_joined_not_labels_applied',sourceHashes=hashes,validCAMExports=len(cam_exports),camObservationEvents=sum(len(x) for x in cam_by_path.values()),distinctCAMReviewedImages=len(cam_by_path),qualityObservationErrorRows=sum(len(v) for v in observations.values()),captureRecords=len(capture),goodImagesWithAnyJoinedEvidence=len(records),goodImagesWithDirectCAMReview=sum(bool(r['camReviewHistory']) for r in records),goodLabelSuspicionFlags=sum('human_label_suspicion_not_confirmed_relabel' in r['reviewFlags'] for r in records),goodVisibilityInterpretationFlags=sum('human_visibility_field_needs_target_damage_interpretation' in r['reviewFlags'] for r in records),twoScopeConflicts=len(direct_scope),originalsModified=False,sourceHashesUnchanged=all(sha(p)==v for p,v in hashes.items()),newModelInference=False,finalTestRead=False,labelsApplied=False,readyForTraining=False)
    summary['unresolvedScopeCases']=sum(not row['scopeResolved'] for row in direct_scope)
    summary['qualityClarificationsAppliedToFutureProposal']=len(clarifications)
    dump(out/'summary.json',summary)
    parts=['<!doctype html><meta charset="utf-8"><title>도어 품질 근거 대조</title><style>body{font:18px sans-serif;max-width:1200px;margin:25px auto}img{max-width:100%;max-height:650px}pre{white-space:pre-wrap}article{border-top:1px solid #aaa;padding:20px 0}</style><h1>도어 품질 근거 대조 — 대상 손상 판단 기록</h1><p>원본 양품 라벨과 기존 ‘결함 확인 가능’ 관찰이 다른 사진입니다. 사진을 누르면 원본을 엽니다. 도어 외측의 손상인지 확인하며 인접 패널 손상을 도어 정답으로 자동 반영하지 않습니다. 이번 대조로 라벨·분할·모델을 바꾸지 않았습니다.</p>']
    for i,row in enumerate(direct_scope):
        with Image.open(row['imagePath']) as source:
            im=ImageOps.exif_transpose(source).convert('RGB');im.thumbnail((1200,850));im.save(out/f'case_{i+1}.jpg',quality=93)
        parts.append('<article><h2>'+html.escape(row['reviewId'])+(' — 사용자 확인: '+html.escape(row['disposition']) if row['scopeResolved'] else '')+'</h2><p>기존 관찰: '+html.escape(row['priorHumanObservation'])+'</p><p>'+html.escape(row['latestUserClarification']['reason'] if row['scopeResolved'] else row['currentAIObservation'])+'</p><a target="_blank" href="'+html.escape(Path(row['imagePath']).as_uri())+'"><img src="case_'+str(i+1)+'.jpg"></a><p>확인할 선택: 도어 손상 / 인접 부품 손상 / 오염·반사 / 판단 보류. 같은 도어 손상이 확인되면 차기 DEFECT 후보로 반영하되 원본 라벨은 보존합니다.</p></article>')
    parts.append('<h2>GOOD 기존 근거 집계</h2><pre>'+html.escape(json.dumps({k:v for k,v in summary.items() if k!='sourceHashes'},ensure_ascii=False,indent=2))+'</pre>')
    page='\n'.join(parts)
    if clarifications:
        page=page.replace('확인할 선택: 도어 손상 / 인접 부품 손상 / 오염·반사 / 판단 보류. 같은 도어 손상이 확인되면 차기 DEFECT 후보로 반영하되 원본 라벨은 보존합니다.','사용자 후속 판단을 위 제목과 설명에 반영했습니다. 실제 원본 라벨과 기존 모델은 변경하지 않았습니다.')
    (out/'index.html').write_text(page)
    report=f'''# 도어 GOOD 품질 근거 병합\n\n기존 CAM 검토 내보내기 {len(cam_exports)}개를 원본 보고서 해시와 대조하고, 반복되는 sample_00 같은 이름이 아닌 이미지 경로로 연결했다. CAM 관찰 {summary['camObservationEvents']}건 / 고유 사진 {summary['distinctCAMReviewedImages']}장, 기존 촬영 검토33장, 오판41장 중 관찰과 검토자 기록이 있는 {summary['qualityObservationErrorRows']}행을 대조했다. 41행 모두 관찰 완료라고 세지 않았다.\n\n현재 GOOD 후보 중 이 자료들과 직접 연결되는 사진은 {len(records)}장, CAM 검토 연결은 {summary['goodImagesWithDirectCAMReview']}장이다. 라벨 의심 표시 {summary['goodLabelSuspicionFlags']}장, 원본 가시성 ‘보임’ 해석 확인 {summary['goodVisibilityInterpretationFlags']}장이 있다. ‘보임’이나 CAM이 관련 있어 보인다는 판단만으로 불량 정답을 만들지 않는다. 결함 가시성·촬영 적합성·라벨 타당성은 서로 다른 근거다.\n\n## 원본 2장 확인\n\n두 JSON은 도어/스크래치/양품이며 결함 bbox·segmentation이 없다. 실제 원본을 열어 확인했지만 사진 하나만으로 경계 자국·반사·오염의 물성을 확정하지 않았다. new_07은 도어와 인접 하단 부품의 범위 구분, new_11은 도어 표면의 찍힘 의심과 반사·오염 구분이 남는다. 기존 관찰은 보존하고 두 장을 ‘확정 GOOD 근거로 사용하기 전 대상 손상 확인’ 목록에 기록했다. 실제 후보 CSV·원본 라벨은 수정하지 않았다.\n\nindex.html의 두 사진에 대해 도어 손상 / 인접 부품 손상 / 오염·반사 / 보류 중 무엇인지 확인하면 추가 판단 근거로 이어갈 수 있다. 원본을 추가 확인해도 불명확하면 보류를 유지하며 강제로 GOOD/DEFECT를 정하지 않는다.\n\n## 기존 촬영 장면 관계 보완\n\n옛 촬영 검토17·68번의 같은 장면 의심 관계가 최근 초안의8개 관계에서 누락된 것을 발견했다. 원래 후보 역할은 train/policy_development로 달랐다. 확정 중복이 아닌 기존 의심 근거로 다시 추가해 같은 역할이 되도록 새 초안을 생성했다. 실제 모델·기존 분할에는 미적용이며 최신 경로는 outputs/door_split_refresh/latest.json을 따른다.\n\n현재 학습 준비 완료로 표시하지 않는다. 나머지 GOOD가 모두 오라벨이거나 지금 직접 검토하지 않은 자료가 전혀 검토되지 않았다는 주장도 하지 않는다. 예전 다른 검토 화면의 완료 여부와 내보낸 파일 확보 여부는 구분한다.\n\n모델·실행 환경 변경 없음. 재현성 관리로 근거 해시·관찰 이력 병합·원본2장 범위 관찰·차기 분할 제약 누락 보완을 기록했다. 새 추론·학습·보정·최종 시험 실행 없음.\n'''
    if clarifications:
        note='사용자 후속 확인을 반영했다. new_07은 도어에서 결함 미관찰로 GOOD 후보 유지, new_11은 반사와 별개로 찍힘 확인으로 차기 DEFECT 후보에 반영했다. 원본 라벨은 유지했고, 전체 촬영 범위 무손상을 인증한 것은 아니다. 아래 재확인 요구 문구는 과거 대조 경과이며 현재 남은 미확인 범위 사례는 '+str(summary['unresolvedScopeCases'])+'건이다.\n\n'
        report='# 최신 사용자 판단 반영\n\n'+note+report
    (out/'REPORT.md').write_text(report);dump(ROOT/'outputs/door_quality_evidence_merge/latest.json',dict(output=str(out),report=str(out/'REPORT.md'),evidencePage=str(out/'index.html'),readyForTraining=False))
    print(json.dumps(dict(output=str(out),**{k:v for k,v in summary.items() if k!='sourceHashes'}),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
