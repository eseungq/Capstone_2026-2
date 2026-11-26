"""Summarize human CAM review, keeping service DEFECT and diagnostic GOOD separate."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from frame_model.check import ROOT
from frame_model.train import dump,write_csv

ALLOWED={'relevance':{'related','partial','unrelated','unknown'},'background':{'observed','not_observed','unknown'},'usefulness':{'useful','limited','not_useful','unknown'}}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('review',type=Path);args=parser.parse_args()
    human=json.loads(args.review.read_text())
    if human.get('schema')!='frame_cam_human_review_v1' or not human.get('reviewer','').strip():raise ValueError('Invalid review identity')
    directory=(ROOT/'outputs/frame_cam_review'/human['review_id']).resolve()
    if directory.parent!=(ROOT/'outputs/frame_cam_review').resolve():raise ValueError('Invalid review path')
    selection=json.loads((directory/'selection.json').read_text());cam=json.loads((directory/'cam_report.json').read_text())
    if cam['review_id']!=human['review_id']:raise ValueError('CAM/review ID differs')
    expected={r['id'] for r in selection['items']}
    if set(human['reviews'])-expected:raise ValueError('Unknown photo IDs')
    rows=[];incomplete=[];photo_rows=[]
    for item in selection['items']:
        ident=item['id'];review=human['reviews'].get(ident,{})
        for key in ['original_visibility','input_visibility']:
            if review.get(key) not in ['clear','weak','unknown']:incomplete.append({'id':ident,'field':key})
        photo_rows.append({'id':ident,'type':item['pair']['defect_type'],'actual':int(item['pair']['actual']),'original_visibility':review.get('original_visibility',''),'input_visibility':review.get('input_visibility',''),'note':review.get('note','')})
        for model in ['unified',item['specialist_id']]:
            r=review.get('models',{}).get(model,{})
            for key,values in ALLOWED.items():
                if r.get(key) not in values:incomplete.append({'id':ident,'model':model,'field':key})
            result=cam['samples'][ident][model]
            rows.append({'id':ident,'type':item['pair']['defect_type'],'image_id':item['source']['image_id'],'model':model,'model_role':'unified' if model=='unified' else 'specialist','actual':int(item['pair']['actual']),'prediction':result['predicted_quality'],'cam_scope':'service_DEFECT_candidate' if result['predicted_quality']=='DEFECT' else 'diagnostic_GOOD_only','relevance':r.get('relevance',''),'background':r.get('background',''),'usefulness':r.get('usefulness',''),'note':r.get('note',''),'layers':';'.join(l['layer']+':'+l['status'] for l in result['layers'])})
    groups={}
    for kind in {r['type'] for r in rows}:
        groups[kind]={}
        for role in ['unified','specialist']:
            groups[kind][role]={}
            for scope in ['all_selected','service_DEFECT_candidate','diagnostic_GOOD_only']:
                subset=[r for r in rows if r['type']==kind and r['model_role']==role and (scope=='all_selected' or r['cam_scope']==scope)]
                groups[kind][role][scope]={'n':len(subset),**{key:dict(Counter(r[key] for r in subset)) for key in ALLOWED}}
    both=[]
    for item in selection['items']:
        pair=[r for r in rows if r['id']==item['id']]
        if all(r['prediction']=='DEFECT' for r in pair):both.append({'id':item['id'],'type':item['pair']['defect_type'],'actual':int(item['pair']['actual']),'unified_usefulness':next(r['usefulness'] for r in pair if r['model_role']=='unified'),'specialist_usefulness':next(r['usefulness'] for r in pair if r['model_role']=='specialist')})
    out=ROOT/'outputs/frame_cam_summary'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    shutil.copyfile(args.review,out/'human_review_original.json')
    report={'review_id':human['review_id'],'reviewer':human['reviewer'],'photos':len(photo_rows),'model_reviews':len(rows),'complete':not incomplete,'incomplete_fields':incomplete,'groups':groups,'both_predicted_DEFECT':both,'original_visibility':dict(Counter(r['original_visibility'] for r in photo_rows)),'input_visibility':dict(Counter(r['input_visibility'] for r in photo_rows)),'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.review,directory/'selection.json',directory/'cam_report.json',Path(__file__)]},'layer_specific_numeric_ratings_available':False,'labels_or_model_changed':False,'limitations':['Purposive error/disagreement sample; not representative performance or CAM pass rate.','Two layers share one model-level rating; notes preserved verbatim, no automatic per-layer numerical conversion.','GOOD CAM is diagnostic only and must not be pooled as service explanations.','Different predicted-DEFECT subsets have different denominators; compare paired cases separately.','One reviewer, no inter-rater agreement established.']}
    dump(out/'summary.json',report);write_csv(out/'model_reviews.csv',rows);write_csv(out/'photo_reviews.csv',photo_rows);write_csv(out/'both_DEFECT_pairs.csv',both)
    lines=['# 프레임 Grad-CAM 사람 검토 취합','',f'사진 {len(photo_rows)}장 / 모델별 평가 {len(rows)}건. 필수 선택 완료: {not incomplete}.','', '## 유형별 기술 집계 — 표본 전체의 모델당 6건','', '| 유형 | 모델 | 유용 | 제한적 | 도움 안 됨 | 판단 불가 |','|---|---|---:|---:|---:|---:|']
    for kind in selection['checkpoints']['unified']['run_config']['config']['inspection_types']:
        for role in ['unified','specialist']:
            c=groups[kind][role]['all_selected']['usefulness']
            lines.append('| '+kind+' | '+('통합' if role=='unified' else '개별')+' | '+' | '.join(str(c.get(k,0)) for k in ['useful','limited','not_useful','unknown'])+' |')
    lines+=['','위 표는 GOOD 진단 CAM도 포함한 입력 기록의 기술 집계입니다. 서비스 CAM 합격률·모델 우열이 아닙니다. summary.json에는 DEFECT 후보와 GOOD 진단을 분리 집계했고 두 모델이 모두 DEFECT인 동일 사진은 별도 CSV로 보존했습니다.','', '## 해석 제한과 관찰','', '- 실링 개별 모델의 설명 유용성 기록은 통합보다 좋은 사례가 있으나, 원본/224 가시성이 약한 사례와 GOOD 진단도 포함돼 일반화하지 않습니다.','- 외관·헤밍 메모에서 layers.2와 layers.3의 반응이 서로 다른 사례가 반복됩니다. 한 레이어가 모든 유형·사진에서 좋다고 확정할 수 없습니다.','- 헤밍 분류 F1이 높아도 미검출 사례13·14와 다른 설명이 유용하다는 뜻은 아닙니다. 분류 성능과 설명 유용성은 별개입니다.','- 홀20번은 원본부터 어떤 결함인지 판단하기 어렵다고 기록됐습니다. 라벨 오류를 확정하거나 정답을 바꾸지 않습니다.','- 0맵으로 이미지가 없는 사례13·17은 계산 실패가 아니라 기록된 ZERO_MAP과 대응합니다.','', '레이어별 관찰은 model_reviews.csv의 메모를 원문 그대로 보존했습니다. 모델 단위 선택값을 각 레이어의 점수로 복제하지 않았습니다.','', '## 다음 작업','', '추가 학습보다 현재24장의 예측/가시성/레이어 메모를 근거로 유형별 모델·레이어 후보와 미해결 항목을 정리합니다. 지금 검토를 반복하거나 레이어를 서비스에 자동 적용하지 않습니다. 독립 자료 확인·현장 촬영 조건·단일/배치 점수 차이·운영 기준은 별도로 남습니다.']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n');dump(ROOT/'frame_model/latest_cam_summary.json',{'directory':str(out),'report':str(out/'SUMMARY.md')})
    print('[CAM HUMAN SUMMARY]',out/'SUMMARY.md');print(json.dumps({'complete':not incomplete,'photos':len(photo_rows),'model_reviews':len(rows),'both_DEFECT_pairs':len(both),'input_visibility':report['input_visibility']},ensure_ascii=False))

if __name__=='__main__':main()
