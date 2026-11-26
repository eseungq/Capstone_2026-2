"""Import human DOOR CAM notes; preserve observations separately from labels/model decisions."""
import argparse,csv,hashlib,json,re,shutil
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def parse_notes(notes):
 patterns={'original_visibility':r'원본\s*가시성\s*([OXox])','input224_visibility':r'224\s*가시성\s*([OXox])','background_response':r'배경\s*반응\s*([OXox])','layer3_usefulness':r'레이어\s*3\s*([OXox])','layer2_usefulness':r'레이어\s*2\s*([OXox])','defect_visible':r'결함\s*([OXox])'}
 return {key:(m.group(1).upper() if (m:=re.search(pattern,notes)) else None) for key,pattern in patterns.items()}
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--layer3-correction-for',action='append',default=[]);args=parser.parse_args();root=Path(__file__).resolve().parents[1];review=load(args.review);report_path=args.report.resolve();report=load(report_path)
 if not report_path.is_relative_to(root/'outputs/door_next_review'):raise ValueError('Expected local report')
 uri=urlparse(review.get('report',''))
 if uri.scheme!='file' or Path(unquote(uri.path)).resolve()!=report_path.parent/'index.html':raise ValueError('Review report URI mismatch')
 if not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip():raise ValueError('Reviewer required')
 items=review.get('items',[]);samples=report['samples'];byid={s['id']:s for s in samples}
 if len(items)!=len(samples) or len({x['id'] for x in items})!=len(samples) or [x['id'] for x in items]!=[s['id'] for s in samples]:raise ValueError('Missing/repeated/reordered case IDs')
 if any(not isinstance(x.get('notes'),str) or not x['notes'].strip() for x in items):raise ValueError('Missing observations')
 corrections=set(args.layer3_correction_for)
 if corrections-set(byid):raise ValueError('Correction points outside report')
 for sample in samples:
  if sha(sample['image_path'])!=sample['image_sha256']:raise ValueError('Original image changed')
 out=root/'outputs/door_cam_observation_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);shutil.copy2(args.review,out/'original_user_export.json');shutil.copy2(report_path,out/'source_gpu_report.json')
 parsed=[];label_issues=[];links=[];notes_by_id={x['id']:x['notes'] for x in items}
 for i,item in enumerate(items):
  ident=item['id'];sample=byid[ident];fields=parse_notes(item['notes']);correction=None
  if ident in corrections:
   fields['layer3_usefulness']='O';fields['layer2_usefulness']='X';correction=dict(caseId=ident,source='user_chat',text='레이어3가 적절',meaning='layer3 appropriate, layer2 inappropriate for the previously identified contradictory note; raw note preserved')
  original_class=1 if sample['kind'] in ('FN','TP') else 0
  if fields['defect_visible'] is not None:
   observed_class=1 if fields['defect_visible']=='O' else 0
   if observed_class!=original_class:label_issues.append(dict(id=ident,kind=sample['kind'],imagePath=sample['image_path'],imageSHA256=sample['image_sha256'],storedClass=original_class,proposedClass=observed_class,status='visible_region_label_review_proposal_not_applied',evidence=item['notes']))
  elif '흠집이 없' in item['notes'] and original_class==1:
   label_issues.append(dict(id=ident,kind=sample['kind'],imagePath=sample['image_path'],storedClass=original_class,proposedClass=None,status='no_scratch_observation_does_not_exclude_other_damage',evidence=item['notes']))
  match=re.search(r'(?:샘플\s*|sample_)(\d+).*동일한\s*사진',item['notes'])
  ref=('sample_'+match.group(1).zfill(4)) if match else (items[i-1]['id'] if i and '위 사진과 동일한 사진' in item['notes'] else None)
  if ref:
   if ref not in byid or ref==ident:raise ValueError('Invalid same-photo note reference')
   other=byid[ref];links.append(dict(sourceCase=ident,referenceCase=ref,imageA=sample['image_path'],imageB=other['image_path'],groupA=sample['group_id'],groupB=other['group_id'],roles=['model_selection','model_selection'],judgment='user_confirmed_same_photo',source='human_review_notes',reason=item['notes'],crossesTrainValidation=False,applied=False))
  parsed.append(dict(id=ident,kind=sample['kind'],image_path=sample['image_path'],group_id=sample['group_id'],original_label=original_class,raw_notes=item['notes'],**fields,layer_judgment_correction=correction))
 dump(out/'observations.json',parsed);dump(out/'label_review_proposals.json',label_issues);dump(out/'confirmed_within_validation_photo_links.json',links);dump(out/'chat_corrections.json',[r['layer_judgment_correction'] for r in parsed if r['layer_judgment_correction']])
 with (out/'observations.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields=['id','kind','image_path','group_id','original_label','raw_notes','original_visibility','input224_visibility','background_response','layer3_usefulness','layer2_usefulness','defect_visible'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(parsed)
 field_counts={field:dict(Counter(r[field] for r in parsed if r[field] is not None)) for field in ['original_visibility','input224_visibility','background_response','layer3_usefulness','layer2_usefulness','defect_visible']}
 result=dict(status='49_case_human_observations_imported_not_model_approved',reviewer=review['reviewer'],recordCount=len(parsed),caseCounts=dict(Counter(r['kind'] for r in parsed)),sourceReview=str(args.review.resolve()),sourceReviewSHA256=sha(args.review),sourceReport=str(report_path),sourceReportSHA256=sha(report_path),exportBinding='report URI plus all ordered case IDs; exporter did not embed report hash',rawNotesPreserved=True,originalImageHashesChecked=len(samples),structuredFieldCounts=field_counts,structuredCountsMeaning='Explicit O/X notes only; omitted free-text fields stay unknown; not localization accuracy or population rates',labelContradictionProposals=sum(x['proposedClass'] is not None for x in label_issues),additionalLabelVisibilityQuestionCount=sum(x['proposedClass'] is None for x in label_issues),samePhotoWithinValidationPairs=len(links),layerCorrectionCases=sorted(corrections),operatingLayerSelected=False,boundarySingleInferenceStillPending=True,labelsChanged=False,groupsApplied=False,modelChanged=False,trainingPerformed=False,finalTestRead=False,apiModelChanged=False)
 dump(out/'summary.json',result)
 (out/'REPORT.md').write_text('''# 新しいDOORの人によるCAM検討
'''.replace('新しいDOORの人によるCAM検討','새 DOOR 모델 사람 검토 결과')+f'''
검토자{review['reviewer']}. 원문49개메모를보존하고정확한report URI·순서·사례ID와원본49장의SHA256을대조했다. 원본내보내기에는report 해시가없어가져오는시점의report 해시를추가기록했다.

## 확인한 관찰

- FN28·FP17·정분류4장 모두메모가작성됐다.
- 정형O/X표현이있는35건중26건은배경반응O다. 전부49장의객관적비율이나전체데이터의통계가아니다.
- 앞부분자유서술에는224축소후가시성저하, 손상과다른영역·반사반응, 레이어별로다른설명등이있다. 모든자유서술을임의로O/X로변환하지않았다.
- sample_0170의서술모순은사용자후속답변“레이어3가적절”로정리했다. 레이어3 O·레이어2 X를유지하고원문과정정근거를분리저장했다.

## 라벨 재확인 제안

명시적결함O/X와저장라벨이충돌하는4건은sample_1148(FN,결함X),sample_0129·0170(FP,결함O),sample_0878(TP,결함X)다. 제안은보이는도어영역의관찰과저장라벨을다시대조할대상이며원본라벨을바꾼것이아니다.

sample_1465의“흠집없음”은다른손상도없다는말과같지않아추가질문대상으로분리하고GOOD으로자동전환하지않았다. sample_0879는0878과같은사진이라는메모로연결했지만이메모만으로결함X를자동전파하지않았다.

## 같은 사진 추가 확인

sample_1293↔1177, sample_0879↔0878은사용자메모에서같은사진으로확인됐다. 현재모두모델선택안에있어직접적인학습/검증교차누수확정은아니다. 그러나같은사진이서로다른대표로그대로남아있어평가표본의반복가중에영향을줄수있다. 그룹·분할은이번가져오기에서바꾸지않고차기그룹제안근거로보존했다. 이2쌍만삭제해점수를다시내도이미모델선택에사용된영향은없어지지않는다.

## 결론과 다음 순서

두레이어가모두맵생성에성공한것과결함을유용하게설명하는것은별개다. 현재관찰만으로운영레이어를자동교체하지않는다. 레이어2가일부사례에유용해도다른사례에는레이어3가더적절하며배경반응이반복된다. 정확한결함위치·면적검출완료로표현하지않는다.

우선미실행인0.5근접사진의단일추론을확인한다. 다음으로위라벨재확인사례와새동일사진2쌍을실험원장에정리해분류오류와라벨문제·설명문제를구분한다. 라벨변경·재학습을즉시반복하지않는다. 분류기준·허용오차·정밀도·확률보정·AUTO_PASS기준을바꾸지않았다.

기존모델·원본·API·분할·DB·최종시험1700장변경없음. 관찰검토완료와독립평가·API배포가능판단은구분한다.
''')
 dump(root/'outputs/door_cam_observation_import/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),humanReviewComplete=True,operatingLayerSelected=False,boundarySingleInferencePending=True))
 print(json.dumps({k:v for k,v in result.items() if k not in ['structuredFieldCounts','structuredCountsMeaning']},ensure_ascii=False,indent=2));print('[CAM NOTES IMPORT]',out)
if __name__=='__main__':main()
