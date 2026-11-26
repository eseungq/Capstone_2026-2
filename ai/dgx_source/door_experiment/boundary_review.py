"""Repeated single-image inference for the 20 nearest model-selection scores to cutoff .5."""
import argparse,csv,hashlib,importlib.metadata,json,math
from datetime import datetime,timezone
from pathlib import Path
from door_experiment.preflight import audit_manifests

def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def nearest_indices(saved,count=20):
 return sorted(range(len(saved)),key=lambda i:(abs(float(saved[i]['raw_defect_score'])-.5),i))[:count]
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();root=Path(__file__).resolve().parents[1];source=args.report.resolve()
 if not source.is_relative_to(root/'outputs/door_next_review'):raise ValueError('Local GPU review report required')
 original=load(source);run=Path(original['run']);cfg=load(run/'run_config.json');best=load(run/'best_metrics.json');tables,_=audit_manifests(root,cfg['manifests']['provenance']['config_path']);rows=tables['model_selection']
 with (run/'best_model_selection_predictions.csv').open(encoding='utf-8-sig',newline='') as f:saved=list(csv.DictReader(f))
 if len(rows)!=len(saved):raise ValueError('Coverage differs')
 for r,s in zip(rows,saved):
  if r['image_path']!=s['image_path'] or r['class_id']!=int(s['class_id']):raise ValueError('Row alignment differs')
 if sha(run/'best.pt')!=original['checkpoint_sha256']:raise ValueError('Checkpoint differs')
 queue_path=source.parent/'boundary_priority_queue.json';queue=load(queue_path)
 if sha(source)!=queue['sourceReportSHA256']:raise ValueError('Source report changed')
 selected=nearest_indices(saved)
 if [saved[i]['image_path'] for i in selected]!=[r['image_path'] for r in queue['items']]:raise ValueError('Nearest-score queue differs')
 import numpy as np,torch,timm
 from PIL import Image,ImageOps
 from torchvision.transforms import functional as TF
 from frame_model.cam_review import verify_metadata,state_hash
 for package,expected in cfg['versions'].items():
  if importlib.metadata.version(package)!=expected:raise ValueError('Environment differs: '+package)
 if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
 torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
 checkpoint=torch.load(run/'best.pt',map_location='cpu',weights_only=False);verify_metadata(checkpoint['metadata'],cfg)
 if checkpoint['epoch']!=best['epoch'] or checkpoint['metrics']!=best:raise ValueError('Not recorded best checkpoint')
 model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2);model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint;model=model.float().cuda().eval();before=state_hash(model)
 out=root/'outputs/door_boundary_review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 result=dict(status='running',sourceReport=str(source),sourceReportSHA256=sha(source),sourceCodeSHA256=sha(Path(__file__)),run=str(run),epoch=best['epoch'],checkpointSHA256=original['checkpoint_sha256'],sampleCount=len(selected),repeats=3,cutoff=.5,cutoffChanged=False,precision='FP32',tolerance={'abs':1e-6,'rel':1e-4},samples=[],trainingPerformed=False,finalTestRead=False,apiModelChanged=False,full1959SingleInferenceVerified=False)
 dump(out/'report.json',result)
 def tensor(path):
  with Image.open(path) as im:display=ImageOps.exif_transpose(im).convert('RGB')
  padded=ImageOps.pad(display,(224,224),method=Image.Resampling.BICUBIC,color=(124,116,104))
  return TF.normalize(TF.to_tensor(padded),[.485,.456,.406],[.229,.224,.225])
 def score(logits):
  if not torch.isfinite(logits).all():raise ValueError('Nonfinite logits')
  values=torch.softmax(logits,dim=1)[:,1].cpu().tolist()
  if any(not math.isfinite(v) or not 0<=v<=1 for v in values):raise ValueError('Invalid scores')
  return values
 old_hashes={r['image_path']:r['sha256'] for r in load(root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json')}
 try:
  batch_cache={};batch_tensors={}
  for index in selected:
   path=rows[index]['image_path']
   if sha(path)!=old_hashes[path]:raise ValueError('Original file changed')
   start=index//8*8
   if start not in batch_cache:
    tensors=[tensor(r['image_path']) for r in rows[start:start+8]];batch_tensors[start]=tensors
    with torch.inference_mode():batch_cache[start]=score(model(torch.stack(tensors).cuda()))
   x=tensor(path);assert torch.equal(x,batch_tensors[start][index-start])
   values=[]
   with torch.inference_mode():
    for repeat in range(3):values.append(score(model(x.unsqueeze(0).cuda()))[0])
   previous=float(saved[index]['raw_defect_score']);batch=batch_cache[start][index-start];classes=[int(v>=.5) for v in values]
   item=dict(index=index,imagePath=path,imageSHA256=old_hashes[path],inputTensorSHA256=hashlib.sha256(x.contiguous().numpy().tobytes()).hexdigest(),batchAndSingleInputEqual=True,classId=int(saved[index]['class_id']),savedBatchScore=previous,recreatedBatchScore=batch,recreatedBatchMatchesSaved=math.isclose(batch,previous,abs_tol=1e-6,rel_tol=1e-4),savedClass=int(saved[index]['predicted_class']),singleScores=values,singleClasses=classes,classChangedFromSaved=any(c!=int(saved[index]['predicted_class']) for c in classes),singleOutsideTolerance=any(not math.isclose(v,previous,abs_tol=1e-6,rel_tol=1e-4) for v in values),repeatScoreRange=max(values)-min(values),repeatClassChanged=len(set(classes))>1,boundaryDistance=abs(previous-.5))
   result['samples'].append(item);dump(out/'report.json',result);print('[BOUNDARY SAMPLE]',index,'saved=',previous,'single=',values,'classes=',classes,flush=True)
  result.update(classChanges=sum(s['classChangedFromSaved'] for s in result['samples']),singleScoreWarnings=sum(s['singleOutsideTolerance'] for s in result['samples']),batchScoreWarnings=sum(not s['recreatedBatchMatchesSaved'] for s in result['samples']),repeatClassChanges=sum(s['repeatClassChanged'] for s in result['samples']),maxSingleSavedAbsoluteDifference=max(abs(v-s['savedBatchScore']) for s in result['samples'] for v in s['singleScores']),modelStateUnchanged=before==state_hash(model),evalMode=not model.training)
  if not result['modelStateUnchanged'] or model.training:raise RuntimeError('Model state changed')
  result['status']='classification_changes_detected' if result['classChanges'] or result['repeatClassChanges'] else ('completed_with_score_warnings' if result['singleScoreWarnings'] or result['batchScoreWarnings'] else 'passed')
 except BaseException as exc:
  result.update(status='failed_or_interrupted',errorType=type(exc).__name__);raise
 finally:
  dump(out/'report.json',result);print('[BOUNDARY REPORT]',out/'report.json',flush=True);print('[BOUNDARY RESULT]',result['status'],flush=True)
 if result['status']=='classification_changes_detected':raise SystemExit(1)
if __name__=='__main__':main()
