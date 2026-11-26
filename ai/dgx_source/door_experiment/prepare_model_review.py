"""CPU-only input checks for the completed 10-epoch DOOR model review."""
import argparse,csv,hashlib,json,math
from pathlib import Path
from door_experiment.preflight import audit_manifests

def load(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args();root=Path(__file__).resolve().parents[1];run=args.run.resolve()
 if not run.is_relative_to(root/'outputs/door_next_training'):raise ValueError('Expected local training artifact')
 cfg=load(run/'run_config.json');best=load(run/'best_metrics.json');status=load(run/'status.json')
 if status['status']!='completed' or cfg['mode']!='train' or cfg['config']['epochs']!=10:raise ValueError('Completed 10-epoch training required')
 config_path=Path(cfg['manifests']['provenance']['config_path']);config=load(config_path)
 if config['experimentVersion']!='door-visible-region-conservative-v3-10epochs':raise ValueError('Unexpected experiment')
 if sha(config_path)!=cfg['manifests']['provenance']['config_sha256']:raise ValueError('Experiment config changed since training')
 tables,audit=audit_manifests(root,config_path)
 for role in ['train','model_selection']:
  if cfg['manifests'][role]['sha256']!=audit[role]['sha256']:raise ValueError('Training/inspection lineage differs')
 with (run/'history.csv').open(encoding='utf-8-sig',newline='') as f:history=list(csv.DictReader(f))
 if [int(r['epoch']) for r in history]!=list(range(1,11)):raise ValueError('History incomplete')
 winner=max(history,key=lambda r:float(r['f1']))
 if int(winner['epoch'])!=best['epoch'] or float(winner['f1'])!=best['f1']:raise ValueError('Best epoch selection differs')
 with (run/'best_model_selection_predictions.csv').open(encoding='utf-8-sig',newline='') as f:pred=list(csv.DictReader(f))
 if len(pred)!=len(tables['model_selection']):raise ValueError('Prediction count differs')
 confusion=dict(tp=0,tn=0,fp=0,fn=0)
 for row,saved in zip(tables['model_selection'],pred):
  if row['image_path']!=saved['image_path'] or row['class_id']!=int(saved['class_id']):raise ValueError('Prediction row order differs')
  score=float(saved['raw_defect_score']);y=int(saved['class_id']);p=int(saved['predicted_class'])
  if not math.isfinite(score) or not 0<=score<=1 or int(score>=.5)!=p:raise ValueError('Invalid saved probability/class')
  if int(saved['correct'])!=int(y==p):raise ValueError('Incorrect saved confusion marker')
  confusion['tp' if y==p==1 else 'tn' if y==p==0 else 'fp' if p==1 else 'fn']+=1
 if confusion!={k:best[k] for k in confusion}:raise ValueError('Confusion differs')
 if sha(root/'door_experiment/train_10.py')!=cfg['training_source_sha256']:raise ValueError('Training source differs')
 report=dict(status='review_inputs_ready_gpu_not_run',run=str(run),experimentConfig=str(config_path),bestEpoch=best['epoch'],checkpointSHA256=sha(run/'best.pt'),configSHA256=sha(config_path),predictionCount=len(pred),expectedReviewSamples=best['fn']+best['fp']+4,expectedFN=best['fn'],expectedFP=best['fp'],correctControls=4,expectedCandidateLayers=['layers.3.blocks.1.norm1','layers.2.blocks.5.norm1'],tolerance={'abs':1e-6,'rel':1e-4},checkpointReloadVerified=False,gpuReviewRun=False,trainingPerformed=False,finalTestRead=False,apiModelChanged=False,independenceEstablished=False)
 if args.output:
  args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('[MODEL REVIEW INPUTS READY]',json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
