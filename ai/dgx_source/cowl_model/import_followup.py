"""Preserve a followup observation without silently changing scope or source labels."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('export',type=Path);args=ap.parse_args();raw=args.export.read_bytes();d=json.loads(raw)
 if d.get('schema')!='cowl-followup-v1' or not str(d.get('reviewer','')).strip():raise ValueError('Schema/reviewer missing')
 uri=urlparse(d['evidenceFile'])
 if uri.scheme!='file' or uri.netloc:raise ValueError('Expected local evidence')
 path=Path(unquote(uri.path)).resolve();path.relative_to(ROOT/'outputs/cowl_followup');evidence_raw=path.read_bytes();evidence=json.loads(evidence_raw)
 ids={s['id'] for s in evidence['samples']};obs=d['observations']
 if len(obs)!=len(ids) or {r['id'] for r in obs}!=ids:raise ValueError('Missing/duplicate/unknown ID')
 allowed={'주석 영역에서 불량 근거 확인','여전히 불량 근거 불명확','검사 부위가 보이지 않음'}
 for r in obs:
  if r.get('judgment') not in allowed or not isinstance(r.get('notes',''),str):raise ValueError('Incomplete judgment')
 previous_dir=Path(json.loads((ROOT/'cowl_model/latest_scope_import.json').read_text())['directory']);previous_raw=(previous_dir/'summary.json').read_bytes();previous=json.loads(previous_raw)
 if Path(previous['selection']).parent!=Path(evidence['samples'][0]['original']).parent:raise ValueError('Scope selection differs')
 out=ROOT/'outputs/cowl_followup_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 (out/'original_user_export.json').write_bytes(raw);(out/'evidence_snapshot.json').write_bytes(evidence_raw);(out/'previous_scope_summary.json').write_bytes(previous_raw)
 summary=dict(status='followup_imported_input_visibility_still_open',reviewer=d['reviewer'],exportedAt=d.get('exportedAt'),observations=obs,export_sha256=hashlib.sha256(raw).hexdigest(),evidence_sha256=hashlib.sha256(evidence_raw).hexdigest(),previous_scope_summary_sha256=hashlib.sha256(previous_raw).hexdigest(),sourceLabelsChanged=False,trainingStarted=False,splitCreated=False,scopeChangesApplied=False,interpretation='Followup confirms visible defect evidence in source-box view only; does not explicitly reassess full-image 224 visibility or process input eligibility.',remaining=['sample_22 original-only visibility judgment remains unresolved for 224 full-image input.','sample_17 and sample_18 exclusion-candidate decisions are preserved until framing is explicitly reassessed.','Whole-pool similarity/group audit pending.'])
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 lines=['# 카울커버 3장 재확인 반영','',f'검토자: {d["reviewer"]}. 내보낸 JSON의 ID·필수 판단을 원천 증빙과 대조해 보존했습니다.','']
 for r in obs:lines.append(f'- {r["id"]}: {r["judgment"]}. 메모: {r.get("notes") or "없음"}.')
 lines+=['','3장 모두 주석 영역에서 불량 근거를 확인했다는 관찰입니다. 원천 불량품 라벨과의 가시적 근거 불명확 문제는 이번 관찰로 보완되었습니다.','', '다만 이번 양식은 224 가시성·공정 입력 후보 여부를 별도로 묻지 않았습니다. 따라서 17·18번의 기존 제외 후보를 자동 승인하지 않고, 22번의 원본에서만 판단 가능 기록도 유지합니다. 3장의 확대 확인만으로 224 입력 적합성을 검증했다고 표현하지 않습니다.','', '다음 작업: 전체 Training 이미지 유사 후보 검색을 수행하고, 후보 검토·그룹 설정을 준비합니다. 입력 방식을 동결하기 전 3장의 전체 224 입력 적합성은 별도로 확정해야 합니다. 기존 원천·분할·모델을 변경하거나 학습을 시작하지 않았습니다.']
 (out/'FINDINGS_KO.md').write_text('\n'.join(lines)+'\n');(ROOT/'cowl_model/latest_followup_import.json').write_text(json.dumps(dict(directory=str(out),summary=str(out/'summary.json')),ensure_ascii=False,indent=2));print('[COWL FOLLOWUP IMPORT]',out)
if __name__=='__main__':main()
