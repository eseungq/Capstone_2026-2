"""Compare nine previously reviewed framing candidates without certifying suitability."""
import hashlib,html,json
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1]
def main():
 capture=ROOT/'ai_api/verification/capture_selection_20261017T172736_078787Z/selection_proposals.json'
 boundary=ROOT/'ai_api/verification/capture_audit_20261017T172917_949346Z/user_boundary_review.json'
 data=json.loads(capture.read_text());bounds=json.loads(boundary.read_text())['records']
 notes={
 'new_04':'기존5번. 좌우 틈과 하단은 보이나 도장면 상단이 화면 위쪽에서 잘림.',
 'new_05':'기존6번. 하단 중심이며 손잡이·상단이 보이지 않음.',
 'new_06':'기존7번. 하단·도어 경계 일부가 보이나 상단이 없음.',
 'new_08':'기존9번. 후방 도어 하단 중심이며 상단과 반대쪽 경계가 충분히 보이지 않음.',
 'new_09':'기존10번. 손잡이·하단은 보이나 상단 잘림과 강한 사선이 있음.',
 'new_13':'기존14번. 상단·하단·한쪽 경계가 비교적 선명하나 반대쪽이 잘림. 더 넓게 촬영해야 하는 구도의 참고 후보.'}
 output=ROOT/'ai_api/verification'/('scope_reference_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
 records=[]
 for r in data:
  if r['selectionProposal']!='PRIMARY_CAPTURE_CANDIDATE':continue
  records.append(dict(id='prior_'+r['id'],imagePath=r['imagePath'],imageSHA256=r['imageSHA256'],priorUserJudgment=r['selectionProposal'],aiBoundaryObservation=notes[r['id']],referenceRole='framing_direction_example_not_accepted' if r['id']=='new_13' else 'boundary_comparison_only',wholeFaceSuitableConfirmed=False))
 for r in bounds:records.append(dict(id='random_'+r['id'],imagePath=r['imagePath'],imageSHA256=r['imageSHA256'],priorUserObservation=r['userObservation'],aiBoundaryObservation='사용자가 기록한 일부 잘림/불완전 범위를 유지. 전체 경계 충족으로 확정하지 않음.',referenceRole='boundary_comparison_only',wholeFaceSuitableConfirmed=False))
 for r in records:
  p=Path(r['imagePath']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['imageSHA256']
  with Image.open(p) as im:image=ImageOps.exif_transpose(im).convert('RGB')
  image.thumbnail((1400,1200));image.save(output/(r['id']+'.jpg'),quality=95)
 report=dict(status='reference_not_certified',sourceHashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [capture,boundary]},observer='AI boundary review; original human judgments preserved',acceptedReferenceImage=None,directionExample='prior_new_13',originalsModified=False,finalTestUsed=False,records=records)
 (output/'reference_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>도어 촬영 기준 비교</title><style>body{font-family:sans-serif;margin:28px;max-width:1400px}img{max-width:100%;width:1000px}article{border-top:2px solid #aaa;padding:20px}p{line-height:1.7}</style><h1>도어 외측 기준 사진 준비</h1><p>9장 비교에서 네 경계가 모두 보이는 합격 기준 사진을 확정하지 못했습니다. 기존14번은 촬영 방향 참고용이며 합격 기준이 아닙니다. 새 경계 기준은 제안이며 기존 사용자 판단을 덮어쓰지 않습니다.</p><h2>촬영 구도 설명도</h2><p>아래는 실제 차량이나 학습 이미지가 아닌 개념도입니다. 도장면의 상단·하단·양끝을 포함하고 검사 대상 문을 구분해야 합니다. 도장면 가장자리 밖 여백을 두되 수치 기준은 아직 없습니다.</p><img style="width:850px" src="framing_guide.svg"><h2>기준 사진 확보 순서</h2><ol><li>앞문/뒷문 중 대상 한 개를 정합니다.</li><li>카메라를 물러서 네 도장면 경계와 주변 여유 영역을 담습니다. 비스듬함 때문에 표면이 숨지 않게 합니다.</li><li>손잡이 주변·하단·경계가 반사나 그림자에 가리지 않는지 확인합니다.</li><li>같은 구도를 반복할 카메라 위치·거리·조명·장비를 기록합니다. 관찰할 최소 결함과224 가시성은 별도로 확인합니다.</li><li>확보한 한 장은 구도 기준 후보로 검토하고, 정상 정답·성능 검증 자료로 자동 취급하지 않습니다.</li></ol><p>새 사진 확보 전 기존 자료는 도어 외관 사진 기반 모의 검사 자료로 유지합니다. 합격 기준 사진을 대신해 인위적으로 배경을 합성하거나 잘린 면을 채우지 않았습니다.</p>']
 for r in records:
  parts.append('<article><h2>'+html.escape(r['id'])+'</h2><p>'+html.escape(r['aiBoundaryObservation'])+'</p><a href="'+html.escape(Path(r['imagePath']).as_uri(),quote=True)+'"><img src="'+r['id']+'.jpg"></a></article>')
 (output/'index.html').write_text('\n'.join(parts))
 (output/'framing_guide.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="640" viewBox="0 0 1000 640"><rect width="1000" height="640" fill="#fff"/><text x="40" y="40" font-family="sans-serif" font-size="24">도어 외측 도장면 촬영 구도 개념도 — 실제 사진 아님</text><rect x="100" y="90" width="800" height="470" fill="#f8fafc" stroke="#64748b" stroke-dasharray="10 8" stroke-width="3"/><path d="M220 180 L740 180 L800 440 Q600 490 260 455 Z" fill="#dbeafe" stroke="#1d4ed8" stroke-width="5"/><rect x="620" y="230" width="95" height="18" rx="8" fill="#64748b"/><g fill="#111" font-size="25" font-family="sans-serif"><text x="380" y="145">상단 도장면 경계</text><text x="390" y="525">하단 도장면 경계</text><text x="130" y="330">한쪽 끝</text><text x="800" y="330">반대쪽 끝</text><text x="325" y="360">검사할 문 한 개의 외측 면</text><text x="120" y="610">네 경계를 잘리지 않게 포함 · 사선/반사로 숨은 면은 검사 완료로 보지 않음</text></g></svg>''')
 print(output)
if __name__=='__main__':main()
