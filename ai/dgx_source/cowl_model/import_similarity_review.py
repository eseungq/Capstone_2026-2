"""Import human identity judgments and propose split constraints without applying them."""
import argparse,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('export',type=Path);args=ap.parse_args();raw=args.export.read_bytes();d=json.loads(raw)
 if d.get('schema')!='cowl-similarity-review-v1' or not str(d.get('reviewer','')).strip():raise ValueError('Missing schema/reviewer')
 uri=urlparse(d['selectionFile'])
 if uri.scheme!='file' or uri.netloc:raise ValueError('Expected local selection')
 selection_path=Path(unquote(uri.path)).resolve();selection_path.relative_to(ROOT/'outputs/cowl_similarity_review');selection_bytes=selection_path.read_bytes();s=json.loads(selection_bytes);pairs={p['review_id']:p for p in s['samples']};obs=d['observations']
 if len(obs)!=len(pairs) or {r['id'] for r in obs}!=set(pairs):raise ValueError('Missing, duplicate or unknown pair IDs')
 allowed={'같은 사진','같은 실물·연속 촬영 의심','다른 사진·실물 관계 불명','판단 보류'}
 source=Path(s['source']);candidate_bytes=(source/'candidates.jsonl').read_bytes()
 if hashlib.sha256(candidate_bytes).hexdigest()!=s['candidate_sha256']:raise ValueError('Source candidates changed')
 fps={r['image_id']:r for r in map(json.loads,(source/'fingerprints.jsonl').read_text().splitlines())};records=[];constraints=[];holds=[];ambiguities=[]
 for r in obs:
  if r.get('judgment') not in allowed or not isinstance(r.get('notes',''),str):raise ValueError('Invalid judgment')
  p=pairs[r['id']];a,b=fps[p['a']],fps[p['b']];record=dict(r,a=p['a'],b=p['b'],a_type=a['type'],b_type=b['type'],a_quality=a['quality'],b_quality=b['quality']);records.append(record)
  if r['judgment'] in {'같은 사진','같은 실물·연속 촬영 의심'}:
   constraints.append(dict(pair_id=r['id'],a=p['a'],b=p['b'],basis='human_same_photo' if r['judgment']=='같은 사진' else 'human_same_part_suspected',action='propose_same_future_split',identityConfirmed=r['judgment']=='같은 사진',applied=False))
  if r['judgment']=='같은 사진' and a['type']==b['type'] and a['quality']!=b['quality']:
   holds.append(dict(pair_id=r['id'],images=[p['a'],p['b']],reason='human_same_photo_same_type_conflicting_source_quality',action='proposed_hold_pending_label_adjudication',applied=False))
  if r['judgment']=='같은 실물·연속 촬영 의심' and '같은 사진' in r.get('notes',''):
   ambiguities.append(dict(pair_id=r['id'],structured=r['judgment'],note=r['notes'],handling='Keep suspected split link; do not promote to confirmed duplicate or discard either image.'))
 out=ROOT/'outputs/cowl_similarity_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 for name,data in [('original_user_export.json',raw),('selection_snapshot.json',selection_bytes),('exact_display_groups_snapshot.json',(selection_path.parent/'exact_display_groups.json').read_bytes())]:(out/name).write_bytes(data)
 def dump(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 dump('observations.json',records);dump('future_split_constraints.json',dict(links=constraints,applied=False,physicalIdentityNotCertified=True));dump('label_hold_proposals.json',holds);dump('judgment_ambiguities.json',ambiguities)
 summary=dict(status='review_imported_label_scope_and_remaining_candidates_open',reviewer=d['reviewer'],exportedAt=d.get('exportedAt'),reviewed_pairs=len(records),judgments=dict(Counter(r['judgment'] for r in records)),cross_type_reviewed=sum(r['a_type']!=r['b_type'] for r in records),same_type_reviewed=sum(r['a_type']==r['b_type'] for r in records),proposed_same_split_links=len(constraints),same_type_conflict_hold_pairs=len(holds),same_type_conflict_hold_images=len({i for h in holds for i in h['images']}),structured_note_identity_ambiguities=len(ambiguities),remaining_nonexact_unreviewed_pairs=s['nonexact_unreviewed_outside_batch'],export_sha256=hashlib.sha256(raw).hexdigest(),selection_sha256=hashlib.sha256(selection_bytes).hexdigest(),sourceLabelsChanged=False,splitChanged=False,imagesDeleted=False,trainingStarted=False)
 dump('summary.json',summary)
 lines=['# 카울커버 유사 사진 32쌍 검토 반영','',f'검토자: {d["reviewer"]}. 32쌍 ID와 판단을 원천 표본 목록에 대조했습니다.','',f'판단 집계: {summary["judgments"]}','',f'차기 분할 동일 역할 제약 제안 {len(constraints)}개. 실제 분할에는 적용하지 않았습니다. 같은 사진 확정과 같은 실물 의심은 별도 근거로 보존했습니다.','', '## 학습 전에 해결할 라벨 범위','', '1~12번은 검사 유형이 다른 정상/불량 후보입니다. 같은 이미지에서 고정핀 정상·연계 불량이 공존할 수 있으므로 서로 다른 유형의 quality 차이 자체는 오라벨이 아닙니다. category 이름은 검사 유형이고 quality가 그 유형의 정상/불량입니다.','', '따라서 두 유형의 quality만 합쳐 사진 전체 GOOD/DEFECT 하나로 바로 학습하면 목표가 서로 충돌할 수 있습니다. 단일 모델을 쓰더라도 검사 유형을 구분한 입력/출력 또는 모든 지정 유형을 관찰한 이미지 단위 정답 설계가 필요합니다. 현재는 통합 이진 라벨을 확정하지 않았습니다.','', '## 같은 사진·같은 유형의 라벨 충돌 보류 제안','']
 for h in holds:lines.append('- '+h['pair_id']+': 두 사진을 차기 학습 보류 후보로 기록. 삭제·GOOD/DEFECT 재지정 없음.')
 lines+=['',f'1~6번은 구조화 판단이 실물 의심인데 메모에는 같은 사진이라고 적혀 있어 {len(ambiguities)}건을 별도 표시했습니다. 현재 보수적인 같은 분할 제약 제안은 유지하되 동일 사진 확정/대표 이미지 제거에는 사용하지 않습니다.','', '다른 사진 5쌍은 실물 독립성 확인으로 확대하지 않습니다. 표본 밖 비동일 픽셀 후보 1,882쌍은 미검토입니다. 동일 픽셀 58그룹은 별도 증빙으로 보존했습니다.','', '다음 우선순위: 통합 모델의 검사 유형별 라벨 설계 정리 → 같은 유형 충돌 4쌍의 원천 주석 비교 → 남은 후보 우선순위·그룹 제약 보완. 전체 독립성·학습 준비 완료로 표시하지 않습니다. 원본·라벨·모델·기존 분할은 변경하지 않았습니다.']
 (out/'FINDINGS_KO.md').write_text('\n'.join(lines)+'\n');dump('artifact_check.json',dict(expectedPairs=len(pairs),validatedPairs=len(records),uniquePairIds=len({r['id'] for r in records}),originalExportBytePreserved=(out/'original_user_export.json').read_bytes()==raw));(ROOT/'cowl_model/latest_similarity_import.json').write_text(json.dumps(dict(directory=str(out),summary=str(out/'summary.json')),ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2));print('[COWL SIMILARITY IMPORT]',out)
if __name__=='__main__':main()
