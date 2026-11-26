"""Reconcile existing human proposals; prepare remaining candidates without applying labels/splits."""
import argparse
import csv
import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageOps
from ai_api.duplicate_groups import ROOT, read_csv

RANK=ROOT/'ai_api/verification/similarity_rank_20261016T183911_041173Z'
REVIEW=ROOT/'ai_api/verification/label_review_import_20261017T042134_367319Z/corrected_user_review.json'
ROUND2=ROOT/'ai_api/verification/split_candidate_20261017T044724_629801Z/user_similarity_review_round2.json'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--groups',type=Path,required=True);args=p.parse_args()
    groups_dir=args.groups.resolve(); group_file=groups_dir/'groups.json'; groups=load(group_file)
    pointer=load(ROOT/'ai_api/verification/latest_data_proposal.json');split_dir=ROOT/pointer['splitDirectory'];draft_dir=ROOT/pointer['representativeDirectory']
    split_summary=load(split_dir/'summary.json')
    for path,expected in split_summary['sourceHashes'].items():
        if digest(path)!=expected:raise ValueError('Split evidence changed: '+path)
    for path,expected in load(groups_dir/'summary.json')['sourceHashes'].items():
        if digest(path)!=expected:raise ValueError('Group evidence changed: '+path)
    old_groups=load(ROOT/pointer['groupDirectory']/'groups.json')
    if old_groups!=groups:raise ValueError('Latest proposal group membership differs')
    rows={r['image_path']:r for r in read_csv(groups_dir/'grouped_manifest.csv')}
    member={path:g['groupId'] for g in groups for path in g['members']}
    review=load(REVIEW); assert review['applied'] is False
    assert digest(review['source'])==review['sourceSHA256']
    correction=load(REVIEW.parent/'corrected_summary.json'); assert digest(REVIEW)==correction['correctedReviewSHA256']
    decisions={r['groupId']:r for r in review['records']}
    assert set(decisions)=={g['groupId'] for g in groups if g['labelConflict']}
    out=ROOT/'outputs/door_evidence_reconciliation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    labels=[];json_checked=0
    for g in groups:
        if not g['labelConflict']:continue
        d=decisions[g['groupId']]; observed=[]
        assert {s['imagePath'] for s in d['sources']}==set(g['members'])
        for s in d['sources']:
            assert digest(s['jsonPath'])==s['jsonSHA256']
            raw=load(s['jsonPath']); json_checked+=1
            qualities={a.get('attributes',{}).get('quality') for a in raw['annotations']};qualities.discard(None)
            assert qualities=={s['quality']}
            source_class={'양품':0,'불량품':1}[s['quality']]
            assert int(rows[s['imagePath']]['class_id'])==source_class
            cats={c['id']:c['name'] for c in raw['categories']}
            annotated_categories=sorted({cats[a['category_id']] for a in raw['annotations']})
            observed.append(dict(imagePath=s['imagePath'],jsonPath=s['jsonPath'],quality=s['quality'],classId=source_class,annotatedCategories=annotated_categories,jsonSHA256=s['jsonSHA256']))
        labels.append(dict(groupId=g['groupId'],caseId=d['id'],decision=d['decision'],proposedClass=d['proposedClass'],reason=d['reason'],visibility=d['visibility'],originalSources=observed,originalLabelsChanged=False,disposition='future_defect_candidate_not_ground_truth_rewrite' if d['decision']=='DEFECT_CANDIDATE' else 'future_hold_capture_not_auto_exclusion_of_all_closeups'))
    ledger=read_csv(draft_dir/'all_images_ledger.csv')
    for r in ledger:
        if r['group_id'] in decisions:
            d=decisions[r['group_id']]
            assert r['review_decision']==d['decision']
            assert r['proposed_class_id']==('' if d['proposedClass'] is None else str(d['proposedClass']))
    reviews=[load(RANK/'user_similarity_review.json'),load(ROUND2)]
    judgments={}
    for rev in reviews:
        assert digest(rev['source'])==rev['sourceSHA256']
        for r in rev['records']:judgments[(r['validation_image'],r['train_image'])]=r['judgment']
    ranked=load(RANK/'ranked_candidates.json'); remaining=[];same_group=0
    roles={r['group_id']:r['future_split'] for r in read_csv(split_dir/'candidate_roles.csv')}
    for r in ranked:
        a,b=r['validation_image'],r['train_image'];assert rows[a]['originalSplit']=='internal_validation' and rows[b]['originalSplit']=='train'
        if member[a]==member[b]:same_group+=1;continue
        ra,rb=roles.get(member[a]),roles.get(member[b])
        remaining.append(dict(r,validationGroup=member[a],trainGroup=member[b],previousJudgment=judgments.get((a,b),'not_reviewed'),proposalRoles=[ra,rb],crossesProposedRoles=bool(ra and rb and ra!=rb)))
    # Ranking is a review convenience, never an identity threshold. Cover distinct validation images.
    remaining.sort(key=lambda r:(not r['crossesProposedRoles'],r['rankScore'],r['validation_image'],r['train_image']))
    queue=[];seen=set()
    for r in remaining:
        if r['validation_image'] in seen:continue
        seen.add(r['validation_image']);queue.append(dict(r,caseId=f'candidate_{len(queue)+1:02d}'))
        if len(queue)==20:break
    dump(out/'label_reconciliation.json',dict(reviewSource=str(REVIEW),reviewSHA256=digest(REVIEW),records=labels,applied=False))
    dump(out/'remaining_candidates.json',remaining);dump(out/'review_queue.json',queue)
    provenance={str(path):digest(path) for path in [group_file,REVIEW,REVIEW.parent/'corrected_summary.json',RANK/'ranked_candidates.json',RANK/'user_similarity_review.json',ROUND2,split_dir/'summary.json',draft_dir/'all_images_ledger.csv',Path(__file__)]}
    summary=dict(status='reconciled_proposals_not_frozen',labelGroups=len(labels),labelDecisionCounts=dict(Counter(r['decision'] for r in labels)),sourceJSONFreshHashChecked=json_checked,sourceQualityClassMismatches=0,existingDraftAgreesWithCorrectedReview=True,rankedPairs=len(ranked),pairsWithinKnownGroup=same_group,remainingPairs=len(remaining),remainingValidationImages=len({r['validation_image'] for r in remaining}),remainingCrossProposedRolePairs=sum(r['crossesProposedRoles'] for r in remaining),previousJudgmentsAmongRemaining=dict(Counter(r['previousJudgment'] for r in remaining)),queuePairs=len(queue),sourceHashes=provenance,originalsModified=False,splitApplied=False,trainingStarted=False,finalTestRead=False,readyForTraining=False)
    dump(out/'summary.json',summary)
    parts=['<!doctype html><meta charset="utf-8"><title>DOOR 남은 유사 후보</title><style>body{font:17px sans-serif;max-width:1100px;margin:25px auto}article{border-top:1px solid #888;padding:20px 0}img{max-width:48%;max-height:400px}textarea{display:block;width:90%;height:60px}select,input,button{font:inherit;margin:10px}button{padding:12px}</style><h1>DOOR 남은 유사 후보 — 20쌍</h1><p>왼쪽: 내부 검증 / 오른쪽: 학습. 같은 사진은 동일 촬영 이미지의 복제·재인코딩에 해당합니다. 같은 부품의 다른 각도·다른 촬영은 별도로 표시하세요. 배경·색상이 비슷한 것만으로 같은 사진으로 판단하지 않습니다. 미확인은 보류하고 원본은 삭제하지 않습니다.</p><label>검토자<input id="reviewer"></label><button id="export">검토 JSON 내보내기</button><p id="message" role="status"></p>']
    for i,r in enumerate(queue):
        parts.append(f'<article><h2>{i+1}번</h2><p>이전 상태: {html.escape(r["previousJudgment"])} / 유사도 정렬 값: {r["rankScore"]:.4f} (동일 판정 기준 아님)</p>')
        for side,key in [('validation','validation_image'),('train','train_image')]:
            name=f'{i+1:02d}_{side}.jpg'
            with Image.open(r[key]) as src:
                im=ImageOps.exif_transpose(src).convert('RGB');im.thumbnail((750,600));im.save(out/name,quality=90)
            parts.append(f'<a href="{html.escape(Path(r[key]).as_uri())}" target="_blank"><img src="{name}" alt="{side}"></a>')
        parts.append(f'<div><label>판단<select id="decision_{i}"><option value="UNREVIEWED">미검토</option value="SAME_PHOTO">같은 사진</option><option value="POSSIBLY_SAME_PART">같은 실물·다른 촬영 의심</option><option value="DIFFERENT">다른 사진·동일 실물 근거 없음</option><option value="UNSURE">판단 보류</option></select></label></div><textarea id="reason_{i}" placeholder="같은 흠집·반사·경계 등 판단 근거"></textarea></article>')
    payload=json.dumps(queue,ensure_ascii=True).replace('<','\\u003c')
    js='''<script>const queue=QUEUE, sourceHash=HASH;const key='door-review-'+sourceHash;function save(){const data={reviewer:document.getElementById('reviewer').value,records:queue.map((r,i)=>({...r,decision:document.getElementById('decision_'+i).value,reason:document.getElementById('reason_'+i).value}))};try{localStorage.setItem(key,JSON.stringify(data))}catch(e){}return data}try{const old=JSON.parse(localStorage.getItem(key)||'null');if(old){document.getElementById('reviewer').value=old.reviewer||'';old.records.forEach((r,i)=>{if(i<queue.length){document.getElementById('decision_'+i).value=r.decision;document.getElementById('reason_'+i).value=r.reason||''}})}}catch(e){}document.addEventListener('input',save);document.addEventListener('change',save);document.getElementById('export').onclick=()=>{const d=save();const reviewed=d.records.filter(r=>r.decision!=='UNREVIEWED');if(!d.reviewer.trim()||!reviewed.length){document.getElementById('message').textContent='검토자와 한 건 이상의 판단을 입력해 주세요.';return}const result={schema:'door-remaining-candidate-review-v1',sourceQueueSHA256:sourceHash,reviewedAt:new Date().toISOString(),applied:false,originalsModified:false,...d};const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='door_remaining_review_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('message').textContent='JSON 다운로드를 요청했습니다. 다운로드 폴더에 파일이 있는지 확인해 주세요. 검토 '+reviewed.length+'/'+queue.length+'건.'};</script>'''
    parts.append(js.replace('QUEUE',payload).replace('HASH',json.dumps(digest(out/'review_queue.json'))));(out/'index.html').write_text('\n'.join(parts))
    report=f'''# DOOR 기존 검토 대조 결과\n\n## 라벨 충돌 — 재검토를 요구하지 않는 기존 결정\n\n10개 그룹의 기존 수정 검토를 확인했다. DEFECT 후보 7개, 촬영 부적합 보류 3개다. 원래 내보내기에서 GOOD으로 선택했던 7개는 사용자 지시로 이미 수정됐으며, 옛 validation.json의 미해결 표시는 그 이전 기록이다. 이를 다시 미결정으로 취급하지 않는다.\n\n원본 JSON 20개의 현재 해시와 annotations.attributes.quality → class_id 연결을 확인했고 불일치 0건이다. 이는 원본 quality를 제대로 옮겼다는 뜻이며 사진 전체의 올바른 정답이라는 보장은 아니다. 같은 사진이 검사 유형별로 양품/불량품 라벨을 달리 가질 수 있다. 부품 전체 손상 검사라는 목표에 맞춘 이미지 단위 라벨 정책을 별도 버전으로 보존해야 한다. 카테고리 목록 전체가 아니라 실제 annotation category_id를 대조했다.\n\n기존 대표 목록 초안도 수정 검토와 일치한다. 다만 차기 실험의 후보이며 현재 모델 정답·학습 manifest에 적용한 것이 아니다. 촬영 부적합 3개 그룹의 과거 결정을 모든 근접 사진 제외로 확대하지 않는다.\n\n## 남은 유사 관계\n\n- 기존 순위 후보 {len(ranked):,}쌍\n- 알려진 같은 그룹 내부 관계 {same_group:,}쌍\n- 다른 그룹 사이 남은 후보 {len(remaining):,}쌍 / 검증 사진 {summary['remainingValidationImages']:,}장\n- 그중 기존 미래 역할 후보를 넘는 관계 {summary['remainingCrossProposedRolePairs']:,}쌍\n\n후보 관계 수는 중복 사진 수가 아니다. 유사도만으로 합치지 않았다. 기존 미래 분할은 미확정 참고안이며 이번에 새 배정하지 않았다. 모든 역할을 넘는 후보 수는 이번 전체 잔여 집계이며, 옛 8,322쌍은 당시 reviewed 제외 규칙으로 만든 대기열 수라 정의가 다르다.\n\nindex.html에는 기존 역할 교차를 우선하고 검증 사진을 중복하지 않은 상위 20쌍을 준비했다. 이는 전체 중복 점검 완료를 뜻하지 않는다. 같은 사진 / 같은 실물 다른 촬영 의심 / 다른 사진 / 보류를 구분하고 근거를 기록한다. 다른 사진이라는 판단만으로 실물 독립성을 확정하지 않는다. 이번 검토는 새 설문 묶음을 끝없이 반복하기 위한 것이 아니라 분할을 막아야 할 관계와 자동 후보의 오검출 양상을 파악하기 위한 제한된 차수다.\n\n## 적용 전 한계\n\n전체 남은 후보와 라벨 의미가 확정되지 않아 학습 준비 완료로 표시하지 않는다. 같은 실물 식별자는 현재 근거만으로 확정할 수 없다. 최종 시험 1,700장을 읽지 않았다. 현재 내부 검증의 모델 선택 노출도 사라지지 않는다.\n\n모델 성능·판정 변경 없음. 실행 환경 변경 없음. 재현성 관리로 근거 해시·라벨 대조·잔여 후보와 검토 화면만 새 폴더에 보존했다.\n'''
    (out/'REPORT.md').write_text(report)
    print(json.dumps(dict(output=str(out),**summary),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
