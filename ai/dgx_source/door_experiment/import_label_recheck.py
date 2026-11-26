"""Preserve visible-region label clarifications as future proposals; never edit raw/frozen labels."""
import argparse,csv,hashlib,json,shutil
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def validate(review,queue,digest):
 if review.get('schema')!='door-visible-label-recheck-v1' or review.get('sourceQueueSHA256')!=digest:raise ValueError('Schema/queue mismatch')
 if review.get('applied') is not False or review.get('originalsModified') is not False:raise ValueError('Expected unapplied decisions')
 if not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip():raise ValueError('Reviewer required')
 datetime.fromisoformat(review['reviewedAt'].replace('Z','+00:00'));records=review.get('records',[]);expected={r['caseId']:r for r in queue}
 if len(records)!=len(queue) or len({r['caseId'] for r in records})!=len(queue):raise ValueError('Missing or duplicate cases')
 for r in records:
  if {k:v for k,v in r.items() if k not in ['decision','reason']}!=expected.get(r['caseId']):raise ValueError('Original metadata changed')
  if r.get('decision') not in ['GOOD_CANDIDATE','DEFECT_CANDIDATE','HOLD'] or not isinstance(r.get('reason'),str) or not r['reason'].strip():raise ValueError('Incomplete decision')
 return records

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);args=parser.parse_args();root=Path(__file__).resolve().parents[1];pointer_path=root/'outputs/door_label_recheck/latest.json';pointer=load(pointer_path);source=Path(pointer['directory']);queue_path=source/'review_queue.json';review=load(args.review);records=validate(review,load(queue_path),sha(queue_path));ss=load(source/'summary.json')
 for path,digest in ss['sourceHashes'].items():
  if sha(path)!=digest:raise ValueError('Review source changed: '+path)
 report=load(ss['sourceGPUReport']);samples={s['id']:s for s in report['samples']};changes=[];decisions=[]
 for r in records:
  proposed={'GOOD_CANDIDATE':0,'DEFECT_CANDIDATE':1,'HOLD':None}[r['decision']]
  for sample in r['samples']:
   if sha(sample['imagePath'])!=sample['imageSHA256'] or sha(sample['jsonPath'])!=sample['jsonSHA256']:raise ValueError('Image/JSON changed')
   gpu=samples[sample['id']];stored=sample['storedTrainingClass']
   item=dict(caseId=r['caseId'],sampleId=sample['id'],imagePath=sample['imagePath'],imageSHA256=sample['imageSHA256'],jsonPath=sample['jsonPath'],jsonSHA256=sample['jsonSHA256'],sourceGroupId=gpu['group_id'],decision=r['decision'],proposedClass=proposed,storedTrainingClass=stored,reason=r['reason'],evidenceScope='visible target DOOR only',originalObservation=sample['originalObservation'],decisionSource='explicit_user_label_recheck',previousSavedConfusion=gpu['kind'],savedPrediction=int(gpu['saved_score']>=.5),effect=('future_hold' if proposed is None else 'future_label_change' if proposed!=stored else 'retain_label'),applied=False)
   decisions.append(item)
   if item['effect']!='retain_label':changes.append(item)
 out=root/'outputs/door_label_recheck_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);shutil.copy2(args.review,out/'original_user_export.json');dump(out/'case_decisions.json',records);dump(out/'image_decisions.json',decisions);dump(out/'future_changes_and_holds.json',changes)
 notes_import=Path(ss['sourceReviewImport']);duplicates=load(notes_import/'confirmed_within_validation_photo_links.json');dump(out/'pending_same_photo_group_links.json',duplicates)
 # A later explicit quality judgment supersedes earlier CAM-note shorthand, without erasing it.
 reconciled=[dict(sampleId=d['sampleId'],previousObservation=d['originalObservation'],latestDecision=d['decision'],latestReason=d['reason'],latestDecisionTakesPriority=True,rawObservationPreserved=True) for d in decisions];dump(out/'observation_reconciliation.json',reconciled)
 result=dict(status='label_recheck_imported_future_changes_only',reviewer=review['reviewer'],reviewedAt=review['reviewedAt'],recordCount=len(records),imageCount=len(decisions),caseDecisionCounts=dict(Counter(r['decision'] for r in records)),imageDecisionCounts=dict(Counter(d['decision'] for d in decisions)),futureLabelChangeImages=sum(d['effect']=='future_label_change' for d in decisions),futureHoldImages=sum(d['effect']=='future_hold' for d in decisions),retainedLabelImages=sum(d['effect']=='retain_label' for d in decisions),labelChangeSamples=[d['sampleId'] for d in decisions if d['effect']=='future_label_change'],holdSamples=[d['sampleId'] for d in decisions if d['effect']=='future_hold'],pendingWithinValidationPhotoLinks=len(duplicates),sourceReview=str(args.review.resolve()),sourceReviewSHA256=sha(args.review),queueSource=str(queue_path),queueSHA256=sha(queue_path),rawLabelsChanged=False,frozenManifestsChanged=False,savedMetricsRewritten=False,modelChanged=False,apiModelChanged=False,trainingPerformed=False,finalTestRead=False,independenceEstablished=False,sourceHashes={str(p):sha(p) for p in [source/'summary.json',queue_path,Path(ss['sourceGPUReport']),notes_import/'confirmed_within_validation_photo_links.json',Path(__file__).resolve()]})
 dump(out/'summary.json',result)
 (out/'REPORT.md').write_text('''# 보이는 도어 라벨 재확인 결과

검토자 김도현.5건·6사진의대기열SHA·사례메타데이터·원본이미지/JSON해시를확인하고원문내보내기를보존했다.

|대상|최신판단|기존학습라벨|제안처리|
|---|---|---|---|
|sample_1465|보류 — 얼룩인지흠집인지어려움|DEFECT|차기실험보류|
|sample_1148|GOOD후보 — 흠집없음|DEFECT|차기라벨변경제안|
|sample_0129|GOOD후보 — 결함없음|GOOD|유지|
|sample_0170|GOOD후보 — 결함없음|GOOD|유지. 레이어3정정은별도설명관찰|
|sample_0878/0879|DEFECT후보 — 긁힘명확|DEFECT|두사진모두라벨유지. 같은사진그룹통합은차기제안|

## 이전 관찰과의 대조

0129·0170의이전CAM메모결함O와0878의결함X는이번명시적재확인으로정리했다. 이전메모를삭제하지않고최신판단과정정근거를함께저장했다. 1465는흠집없음이라는이전표현을GOOD확정으로확대하지않고보류했다. 제안기준은사진에보이는대상도어이며보이지않는면·기능적결함까지보장하지않는다.

## 점수에 대한 의미

1148은기존FN이었지만최신GOOD후보라벨을가정하면TN에해당한다. 1465는기존FN이나현재판단을보류했으므로새실험평가대상에그대로확정해두면안된다. 나머지4사진은기존라벨을유지한다. 이는어떤기존오판이실제분류오류인지구분할근거이며, 모델성능이개선됐다는증거가아니다.

이번사례는오판위주로골라사후검토했다. 해당사진만빼거나라벨을바꿔새정확도/F1을운영성능처럼발표하지않는다. 기존best_metrics.json·저장예측·97.70%/F197.91%는당시고정라벨의모델선택결과로그대로보존한다. 독립최종평가로격상하지않는다.

## 같은 사진과 후속 범위

1293↔1177,0879↔0878의같은사진관계는모델선택안의반복이다. 학습/검증교차누수라고확대하지않되평가가중에영향을줄수있어차기그룹근거로유지한다. 이번가져오기로원본·동결분할·모델을수정하지않았다.

다음은이제안과동일사진근거를차기데이터변경원장에모아두고, 배경·반사반응과레이어설명적절성을별도문제로정리하는일이다. CAM레이어를자동교체하거나라벨검토때마다재학습을반복하지않는다. 경계20장단일추론검사는분류변경0·점수경고유지로별도보존한다.

원본이미지·JSON·기존모델·학습/검증분할·API·SQLite·최종시험1700장변경없음. 보정·AUTO_PASS·최종PASS/FAIL을추가하지않았다.
''')
 dump(root/'outputs/door_label_recheck_import/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),futureChangesOnly=True,trainingStarted=False));pointer.update(reviewed=True,importDirectory=str(out),caseDecisionCounts=result['caseDecisionCounts']);dump(pointer_path,pointer)
 print(json.dumps({k:v for k,v in result.items() if k!='sourceHashes'},ensure_ascii=False,indent=2));print('[LABEL IMPORT]',out)
if __name__=='__main__':main()
