"""Reconcile existing capture observations with current DOOR GOOD proposals; no relabeling."""
import csv
import hashlib
import html
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.duplicate_groups import ROOT,read_csv


def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def write(p,rows,fields):
    with Path(p).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def note_evidence(notes):
    # Narrow review scheduling flags; never a classifier or automatic label edit.
    negative=any(token in notes for token in ('결함없음','결함 없음'))
    positive=any(token in notes for token in ('결함 확인 가능','결함 작아서 원본에서만 확인 가능'))
    if positive and negative:return 'conflicting_free_text_requires_reconciliation'
    if negative:return 'written_no_defect_observation_not_full_scope_certification'
    if positive:return 'written_defect_observation_requires_label_reconciliation'
    return 'capture_only_or_insufficient_quality_evidence'


def main():
    ready_dir=Path(load(ROOT/'outputs/door_data_readiness/latest.json')['output']);ready=load(ready_dir/'summary.json');ledger_path=ready_dir/'label_proposal_ledger.csv';ledger=read_csv(ledger_path);good={r['image_path']:r for r in ledger if r['proposed_image_class']=='0'}
    capture_dir=ROOT/'ai_api/verification/capture_consolidated_20261017T181937_234097Z';capture_path=capture_dir/'all_reviewed_images.csv';capture_summary=load(capture_dir/'summary.json')
    sources=[ledger_path,ready_dir/'summary.json',capture_path,capture_dir/'summary.json',capture_dir/'decision_history.json',ROOT/'configs/door_image_label_policy_v1.json',ROOT/'ai_api/verification/latest_data_proposal.json',Path(__file__).resolve()]
    hashes={str(p):sha(p) for p in sources}
    for path,expected in capture_summary['sourceHashes'].items():
        if sha(path)!=expected:raise ValueError('Capture evidence changed: '+path)
        hashes[path]=expected
    selection_summary=load(ROOT/'ai_api/verification/capture_selection_20261017T172736_078787Z/summary.json');export=Path(selection_summary['sourceExport'])
    if sha(export)!=selection_summary['sourceExportSHA256']:raise ValueError('Original human export changed')
    hashes[str(export)]=sha(export)
    captures=read_csv(capture_path);all_paths={r['image_path'] for r in ledger};capture_good=[]
    for r in captures:
        if r['image_path'] not in all_paths:raise ValueError('Capture image outside train/internal')
        if sha(r['image_path'])!=r['source_image_sha256']:raise ValueError('Reviewed image changed')
        if r['image_path'] not in good:continue
        current=good[r['image_path']]
        if sha(current['json_path'])!=current['json_sha256']:raise ValueError('Source JSON changed')
        capture_good.append(dict(image_path=r['image_path'],current_group_id=current['group_id'],original_class_id=current['original_class_id'],current_proposed_class_id=current['proposed_image_class'],review_id=r['last_display_id'],capture_status=r['capture_status'],target_door=r['target_door'],notes=r['capture_notes'],note_evidence=note_evidence(r['capture_notes']),full_quality_good_confirmed=False,source_review=r['latest_review']))
    conflicts=[r for r in capture_good if r['note_evidence']=='written_defect_observation_requires_label_reconciliation']
    # Read original user observations for the exact two flags, not model scores.
    selection_path=ROOT/'ai_api/verification/capture_selection_20261017T172736_078787Z/selection_proposals.json';selections={r['imagePath']:r for r in load(selection_path)}
    for r in conflicts:
        e=selections[r['image_path']];assert e['observation']['notes']==r['notes'] and e['imageSHA256']==sha(r['image_path'])
        r.update(source_visibility224=e['observation']['visibility224'],source_coverage=e['observation']['coverage'],source_readability=e['observation']['readability'],recommended_next_action='reconcile_damage_scope_and_quality_before_future_GOOD_use',future_defect_candidate=True,applied=False)
    direct={r['image_path'] for r in capture_good};reviewed_groups={r['current_group_id'] for r in capture_good}
    grouped_good=[r for r in good.values() if r['group_id'] in reviewed_groups]
    untouched=[r for r in good.values() if r['image_path'] not in direct]
    out=ROOT/'outputs/door_good_evidence'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    write(out/'existing_good_capture_evidence.csv',capture_good,list(dict.fromkeys(k for row in capture_good for k in row)));dump(out/'label_observation_conflicts.json',conflicts)
    write(out/'good_without_direct_capture_record.csv',untouched,list(ledger[0]))
    parts=['<!doctype html><meta charset="utf-8"><title>GOOD와 기존 관찰의 불일치'+'</title><style>body{font:18px sans-serif;max-width:1100px;margin:30px auto}img{max-width:100%;max-height:600px}pre{white-space:pre-wrap}</style><h1>GOOD 후보와 기존 관찰의 불일치 2건</h1><p>새 판정 화면이 아니라 기존 근거 대조 자료입니다. 원래 quality와 관찰은 보존했습니다. 자동 라벨 변경은 하지 않았습니다.</p>']
    for i,r in enumerate(conflicts):
        with Image.open(r['image_path']) as src:
            image=ImageOps.exif_transpose(src).convert('RGB');image.thumbnail((1100,750));image.save(out/f'case_{i+1}.jpg',quality=92)
        parts.append(f'<h2>{html.escape(r["review_id"])}</h2><p>{html.escape(r["notes"])}</p><a target="_blank" href="{html.escape(Path(r["image_path"]).as_uri())}"><img src="case_{i+1}.jpg"></a><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre>')
    (out/'index.html').write_text('\n'.join(parts))
    summary=dict(status='existing_evidence_reconciled_not_label_applied',sourceHashes=hashes,currentSourceOnlyGoodRows=len(good),existingCaptureRecords=len(captures),directGoodCaptureRecords=len(capture_good),acceptedCaptureGoodRecords=sum(r['capture_status']=='ACCEPTED_CAPTURE_CANDIDATE' for r in capture_good),goodObservationFlagCounts=dict(Counter(r['note_evidence'] for r in capture_good)),qualityObservationConflicts=len(conflicts),fullScopeGoodCertificationsFromThisAudit=0,goodRowsWithoutDirectCaptureRecord=len(untouched),knownGoodRowsInReviewedGroups=len(grouped_good),reviewedImageHashesRechecked=len(captures),sourceHashesUnchanged=all(sha(p)==v for p,v in hashes.items()),originalLabelsModified=False,splitApplied=False,modelChanged=False,newInferenceExecuted=False,finalTestRead=False,newMandatoryExternalTeamRequests=0,readyForTraining=False)
    dump(out/'summary.json',summary)
    report=f'''# GOOD 후보 기존 검토 대조 — 1차\n\n현재 이미지 단위 제안의 GOOD 행 {len(good):,}장과 기존 촬영 검토33장을 대조했다. 같은 경로의 직접 검토 기록은 {len(capture_good)}장이고, 그중 구도 사용 가능 후보는 {summary['acceptedCaptureGoodRecords']}장이다. 검토 원본 내보내기 SHA와33장 현재 이미지 해시를 확인했다. 구도 통과는 이미지 전체 품질 GOOD 확정이 아니다.\n\n## 확인이 필요한 기존 관찰 2건\n\n'''
    for r in conflicts:report+=f"- {r['review_id']}: 원본 quality GOOD / 기존 관찰 ‘{r['notes']}’ / 224 가시성 ‘{r['source_visibility224']}’.\n"
    report+=f'''\n이 두 건은 이미 기록된 사용자 관찰과 GOOD 원본 라벨의 불일치 후보다. 같은 사진 원본 해시와 기존 내보내기 근거가 맞는다. 새 시각 판정·재추론을 한 것은 아니며, 결함이 우리 검사 대상에 해당하는지 확인한 뒤 차기 DEFECT 후보로 반영해야 한다. 이 작업에서는 라벨·대표 목록·분할을 바꾸지 않았다. 원본에서만 보인다는 관찰은224 입력의 한계 검토 근거이지 이미지의 손상을 지우는 근거가 아니다.\n\n## 나머지 GOOD 근거의 한계\n\n‘결함 없음’ 기록도 촬영 표면 전체나 검사 대상 도어가 확정됐다는 보장은 아니다. 구도만 확인한 기록과 품질 관찰을 분리했다. 직접 촬영 검토 기록이 없는 GOOD 행은 {len(untouched):,}장이지만, 이것이 전부 오라벨 또는 불량이라는 뜻은 아니다. 현재 이1차 대조에서 전체 검사 범위 무손상을 새로 인증한 사진은0장이다. CAM 해석·오판 관찰 등 다른 근거가 아직 통합되지 않았으므로 ‘모든 사람 검토가 없었다’는 주장도 하지 않는다.\n\n다음 작업은 두 불일치 후보의 원본·대상 손상 의미를 우선 확인하고, GOOD 촬영/품질 근거의 부족한 층을 기존 CAM·오판 기록과 더 대조하는 것이다. 모든 GOOD 사진을 한꺼번에 재검토하거나 자동으로 DEFECT로 바꾸지 않는다.\n\n## 다른 팀원에게 지금 요청할 사항\n\n새 필수 요청은 없다. 승규님에게 실제 응답3종/모델 버전과0·상수맵 의미를 전달하고 회신을 기다리는 것으로 현재 팀 협의는 충분하다.\n\n- 승인님: 새 기능 개발을 따로 요청할 필요는 없다. 백엔드가0·상수맵 조회 형식을 정하면 합의한 안내 문구와 함께 앱 표시를 맞춘다.\n- 남균님: 데이터 정제·오판 검토를 진행하는 데 새 DB 자료는 필요 없다. 이후 검사항목 코드·모델/보정/정책·판정 이력 저장을 백엔드와 맞출 때 기존 요청 범위로 협의한다.\n- 실제 서버 주소·유효한 이미지 URL·시간은 다음 주 공동 시험 준비 때 맞춘다. 이번 주 파싱 검증이나 현재 데이터 점검의 선행 조건으로 요구하지 않는다.\n\n데이터 기준과 라벨 후보는 AI 파트에서 먼저 근거를 정리한다. 팀원이 결정해야 하는 서비스·DB 표현을 대신 확정하지 않는다. 기존 모델/API 검증 결과와 현재 데이터 제안을 혼동하지 않는다.\n\n모델 성능·판정 변경 없음. 실행 환경 변경 없음. 재현성 관리로 기존 검토의 경로/해시·현재 라벨 제안 대조·불일치2건과 범위 한계를 새 결과로 보존했다. 최종 시험은 읽지 않았다.\n'''
    (out/'REPORT.md').write_text(report)
    dump(ROOT/'outputs/door_good_evidence/latest.json',dict(output=str(out),report=str(out/'REPORT.md'),evidencePage=str(out/'index.html'),readyForTraining=False))
    print(json.dumps(dict(output=str(out),**summary),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
