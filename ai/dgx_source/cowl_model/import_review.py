"""Validate and preserve a human scope export; never mutate source labels."""
import argparse,csv,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'targetVisible':{'충분히 보임','일부 부족','보이지 않음'},'visibility224':{'224에서도 판단 가능','원본에서만 판단 가능','판단 어려움'},'framing':{'공정 입력 후보','보조 후보','제외 후보'},'labelAgreement':{'원천 라벨에 동의','라벨 불일치 의심','판단 보류'}}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('export',type=Path);args=ap.parse_args()
 raw=args.export.read_bytes();d=json.loads(raw)
 if d.get('schema')!='cowl-scope-review-v1' or not str(d.get('reviewer','')).strip():raise ValueError('Missing schema/reviewer')
 uri=urlparse(d['selectionFile'])
 if uri.scheme!='file' or uri.netloc:raise ValueError('Expected local selection file')
 selection=Path(unquote(uri.path)).resolve();selection.relative_to(ROOT/'outputs/cowl_scope_review')
 sb=selection.read_bytes();source=json.loads(sb);samples={r['id']:r for r in source['samples']};obs=d['observations'];ids=[r['id'] for r in obs]
 if len(ids)!=len(set(ids)) or set(ids)!=set(samples):raise ValueError('Missing, duplicate or unexpected sample IDs')
 records=[]
 for r in obs:
  for field,values in ALLOWED.items():
   if r.get(field) not in values:raise ValueError(f'Incomplete or invalid {r["id"]}: {field}')
  if not isinstance(r.get('notes',''),str):raise ValueError('Invalid notes')
  s=samples[r['id']];records.append(dict(r,image_id=s['image_id'],annotation_types=s['annotation_types'],source_quality=s['source_quality'],image_sha256=s['image_sha256'],image_member=s['image_member']))
 out=ROOT/'outputs/cowl_scope_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 (out/'original_user_export.json').write_bytes(raw);(out/'selection_snapshot.json').write_bytes(sb)
 with (out/'observations.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
 summary=dict(status='human_scope_review_imported_not_training_ready',reviewer=d['reviewer'],exportedAt=d.get('exportedAt'),reviewed=len(records),export_sha256=hashlib.sha256(raw).hexdigest(),selection_sha256=hashlib.sha256(sb).hexdigest(),selection=str(selection),framing=dict(Counter(r['framing'] for r in records)),byType={t:dict(Counter(r['framing'] for r in records if r['annotation_types']==t)) for t in sorted({r['annotation_types'] for r in records})},followup=[r for r in records if r['framing']!='공정 입력 후보' or r['labelAgreement']!='원천 라벨에 동의' or r['visibility224']!='224에서도 판단 가능'],originalLabelsChanged=False,splitChanged=False,trainingStarted=False)
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 lines=['# 카울커버 32장 검토 결과','',f'검토자: {d["reviewer"]}. 입력 JSON의 32개 ID와 필수 응답을 표본 출처와 대조했습니다.','',f'사진 사용 판단: {summary["framing"]}','', '## 후속 확인','']
 for r in summary['followup']:lines.append(f'- {r["id"]}: {r["annotation_types"]} / 원천 {r["source_quality"]} / {r["framing"]} / {r["visibility224"]} / {r["labelAgreement"]}. 관찰: {r["notes"] or "메모 없음"}')
 lines+=['','17·18번의 불량 근거가 불명확하다는 관찰을 오라벨 확정이나 GOOD 변경으로 처리하지 않았습니다. 원천 주석·구축 가이드와 비교할 보류 사례입니다. 22번은 입력 축소의 영향을 확인할 사례입니다.','', '이 결과는 32장에 대한 사용자 관찰입니다. 전체 20,386장의 사용 가능 비율이나 224 성능을 보장하지 않습니다. 원천 라벨·데이터·기존 분할·모델은 변경하지 않았습니다.','', '다음 순서: 보류 2장과 224 한계 1장의 원천 주석·유형 정의 확인 → 전체 이미지 동일/유사 후보와 그룹 근거 점검 → 분할·입력·평가 설정 동결. 학습과 AUTO_PASS는 시작하지 않았습니다.']
 (out/'FINDINGS_KO.md').write_text('\n'.join(lines)+'\n');(ROOT/'cowl_model/latest_scope_import.json').write_text(json.dumps(dict(directory=str(out),summary=str(out/'summary.json')),ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2));print('[COWL IMPORT]',out)
if __name__=='__main__':main()
