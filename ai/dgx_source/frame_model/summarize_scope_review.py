"""Preserve and summarize exported human reviews without changing training data."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from frame_model.check import ROOT
from frame_model.train import dump,write_csv

DECISIONS={'process_candidate':'공정 입력 후보','auxiliary_candidate':'보조 학습 후보','hold':'보류','exclude_candidate':'제외 후보'}
ALLOWED={'decision':set(DECISIONS),'coverage':{'sufficient','partial','unjudgeable'},'visibility224':{'sufficient','lost','unknown'},'capture':{'none','crop','angle','lighting','blur','multiple'},'label_match':{'consistent','suspect','unknown'}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review',type=Path)
    args=parser.parse_args()
    data=json.loads(args.review.read_text())
    directory=ROOT/'outputs/frame_scope_review'/data['review_id']
    if directory.parent != ROOT/'outputs/frame_scope_review': raise ValueError('Invalid review directory')
    bundle=json.loads((directory/'selection.json').read_text())
    if data.get('review_id')!=bundle['review_id'] or data.get('schema')!=bundle['schema']:raise ValueError('Review identity differs')
    if not str(data.get('reviewer','')).strip():raise ValueError('Reviewer missing')
    expected={r['id'] for r in bundle['items']}
    if set(data['reviews'])-expected:raise ValueError('Unknown review IDs')
    incomplete=[];flags=[];rows=[];counts={}
    for item in bundle['items']:
        r=data['reviews'].get(item['id'],{})
        missing=[k for k,choices in ALLOWED.items() if r.get(k) not in choices]
        if missing:incomplete.append({'id':item['id'],'fields':missing})
        row={'id':item['id'],'type':item['defect_type'],'source_class_id':item['class_id'],'image_sha256':item['image_sha256'],**{k:r.get(k,'') for k in ALLOWED},'note':r.get('note','')}
        rows.append(row)
        reasons=[]
        if r.get('visibility224')=='lost':reasons.append('224_input_information_loss')
        if r.get('label_match') in ['unknown','suspect']:reasons.append('source_label_unresolved')
        if r.get('decision')=='exclude_candidate' and not r.get('note','').strip():reasons.append('exclusion_reason_missing')
        if reasons:flags.append({'id':item['id'],'type':item['defect_type'],'reasons':reasons,'decision_unchanged':r.get('decision')})
    for kind in bundle['scopes']:
        rs=[r for r in rows if r['type']==kind]
        counts[kind]={k:sum(r['decision']==k for r in rs) for k in DECISIONS}
        counts[kind]['by_class']={quality:dict(Counter(r['decision'] for r in rs if r['source_class_id']==quality)) for quality in ['0','1']}
    pending=[kind for kind in bundle['scopes'] if data.get('scopes',{}).get(kind,{}).get('status') not in ['provisional','revise','unknown']]
    out=ROOT/'outputs/frame_scope_summary'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    shutil.copyfile(args.review,out/'human_review_original.json')
    report={'review_id':data['review_id'],'reviewer':data['reviewer'],'source_file':str(args.review),'source_sha256':hashlib.sha256(args.review.read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256((directory/'selection.json').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'complete_photo_reviews':len(rows)-len(incomplete),'total_photos':len(rows),'incomplete_photo_fields':incomplete,'scope_decisions_pending':pending,'counts':counts,'flags':flags,'dataset_or_labels_modified':False,'scope_finalized':False}
    dump(out/'summary.json',report);write_csv(out/'photo_decisions.csv',rows)
    lines=['# 프레임 사진 검토 취합','',f'사진 필수 항목 완료: {len(rows)-len(incomplete)}/{len(rows)}. 원본·라벨·분할 변경 없음.','', '| 유형 | 공정 후보 | 보조 후보 | 보류 | 제외 후보 |','|---|---:|---:|---:|---:|']
    for kind,c in counts.items():lines.append('| '+kind+' | '+' | '.join(str(c[k]) for k in DECISIONS)+' |')
    lines+=['','## 확인할 내용','',f'유형별 범위 판단 미선택: {", ".join(pending) or "없음"}. provisional은 잠정 동의이며 실제 공정 검증 완료가 아닙니다.','', '224 정보 소실 사진: '+', '.join(r['id'] for r in rows if r['visibility224']=='lost'),'라벨 의심/판단 불가 사진: '+', '.join(r['id'] for r in rows if r['label_match'] in ['suspect','unknown']), '제외 후보: '+', '.join(r['id'] for r in rows if r['decision']=='exclude_candidate'),'제외 사유 미기록: '+', '.join(r['id'] for r in rows if r['decision']=='exclude_candidate' and not r['note'].strip()),'','사진의 공정 입력 적합성과 현재 224 입력에서의 가시성은 별도로 판단합니다. 라벨 의심/판단 불가는 원천 라벨 오류 확정이 아닙니다. 후보와 판단은 원본·학습 목록에 자동 반영하지 않습니다.','', '이 결과는 64장 표본 검토입니다. 전체 자료 사용 가능 여부나 클래스별 촬영 조건 편향이 해소됐다는 근거가 아닙니다. 추가 전체 학습은 실행하지 않았습니다.']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    dump(ROOT/'frame_model/latest_scope_summary.json',{'directory':str(out),'report':str(out/'SUMMARY.md')})
    print('[SCOPE SUMMARY]',out/'SUMMARY.md');print(json.dumps({'complete':report['complete_photo_reviews'],'total':len(rows),'counts':{k:{a:v for a,v in c.items() if a!='by_class'} for k,c in counts.items()},'scope_decisions_pending':pending},ensure_ascii=False))

if __name__=='__main__':main()
