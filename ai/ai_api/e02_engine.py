"""Separate strict-loaded e02 development engine. Legacy prototype.Engine is unchanged."""
import ast,hashlib,importlib.metadata,json,random,os
from pathlib import Path
from prototype.engine import Engine as LegacyEngine,sha
from door_experiment.preflight import audit_manifests

ROOT=Path(os.environ.get('AI_PROJECT_ROOT',Path(__file__).resolve().parents[1])).expanduser().resolve()
MANIFEST=Path(os.environ.get('AI_CANDIDATE_MANIFEST',ROOT/'ai_api/door_e02_candidate.json'))

def validate_candidate(path=MANIFEST):
 manifest=json.loads(Path(path).read_text())
 for name,expected in manifest.get('reusedCodeSHA256',{}).items():
  if sha(ROOT/name)!=expected:raise ValueError('Reused implementation changed: '+name)
 if manifest['schema']!='door-e02-development-candidate-v1' or manifest['partCode']!='DOOR' or manifest['modelVersion'].startswith('mock-'):raise ValueError('Invalid development model manifest')
 run=(ROOT/manifest['run']).resolve()
 if not run.is_relative_to(ROOT/'outputs/door_next_training'):raise ValueError('Untrusted run path')
 if sha(run/'run_config.json')!=manifest['runConfigSHA256'] or sha(run/'best.pt')!=manifest['checkpointSHA256']:raise ValueError('Candidate bytes changed')
 if sha(ROOT/manifest['trainingSource'])!=manifest['trainingSourceSHA256'] or sha(ROOT/manifest['sourceReview'])!=manifest['sourceReviewSHA256']:raise ValueError('Training/review lineage changed')
 cfg=json.loads((run/'run_config.json').read_text());best=json.loads((run/'best_metrics.json').read_text());review=json.loads((ROOT/manifest['sourceReview']).read_text())
 if cfg['class_mapping']!={'양품':0,'불량품':1} or best['epoch']!=manifest['expectedEpoch'] or review['checkpoint_sha256']!=manifest['checkpointSHA256']:raise ValueError('Class/epoch/review mismatch')
 if manifest['gradcamLayer']!='layers.3.blocks.1.norm1':raise ValueError('Inherited CAM layer must remain unchanged')
 if cfg['config']['model_name']!='swin_tiny_patch4_window7_224.ms_in1k' or cfg['config']['image_size']!=224 or cfg['config']['amp'] or cfg['config']['prediction_cutoff']!=.5:raise ValueError('Inference settings differ')
 tables,_=audit_manifests(ROOT,cfg['manifests']['provenance']['config_path']);allowed={r['image_path'] for r in tables['model_selection']}
 for sample in manifest['samples']:
  if sample['image_path'] not in allowed or sha(Path(sample['image_path']))!=sample['image_sha256']:raise ValueError('Fixture outside frozen selection or changed')
 return manifest,run,cfg

class CandidateEngine(LegacyEngine):
 def __init__(self,manifest_path=MANIFEST):
  manifest,run,cfg=validate_candidate(manifest_path)
  import numpy as np,torch,timm
  from PIL import Image,ImageOps
  from torch.utils.data import Dataset
  from torchvision.transforms import functional as TF
  from timm.data import resolve_model_data_config
  versions={p:importlib.metadata.version(p) for p in cfg['versions']}
  if versions!=cfg['versions'] or not torch.cuda.is_available():raise RuntimeError('Recorded GPU environment required; no fallback')
  self.torch,self.np=torch,np;self.checkpoint_path=run/'best.pt';self.expected_checkpoint_sha256=manifest['checkpointSHA256'];self.candidate_manifest=manifest
  random.seed(42);np.random.seed(42);torch.manual_seed(42);torch.cuda.manual_seed_all(42);torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
  checkpoint=torch.load(self.checkpoint_path,map_location='cpu',weights_only=False)
  if json.loads(json.dumps(checkpoint['metadata']))!=cfg or checkpoint['epoch']!=manifest['expectedEpoch']:raise RuntimeError('Checkpoint metadata differs')
  self.model=timm.create_model(cfg['config']['model_name'],pretrained=False,num_classes=2);self.model.load_state_dict(checkpoint['model_state_dict'],strict=True);del checkpoint;self.model=self.model.float().cuda().eval()
  dc=resolve_model_data_config(self.model);mean,std=dc['mean'],dc['std'];self.fill=tuple(round(v*255) for v in mean)
  if list(mean)!=[.485,.456,.406] or list(std)!=[.229,.224,.225] or cfg['normalization']!={'mean':list(mean),'std':list(std)} or tuple(dc['input_size'])!=(3,224,224) or self.fill!=(124,116,104):raise RuntimeError('Preprocessing differs')
  source=ROOT/manifest['trainingSource'];tree=ast.parse(source.read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');node=next(n for n in main.body if isinstance(n,ast.ClassDef) and n.name=='DoorDataset');ns=dict(Dataset=Dataset,Image=Image,ImageOps=ImageOps,TF=TF,CONFIG=cfg['config'],mean=mean,std=std,fill=self.fill);exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns);self.dataset=ns['DoorDataset']
  self.metadata=dict(model_name=cfg['config']['model_name'],model_sha256=self.expected_checkpoint_sha256,checkpoint_epoch=manifest['expectedEpoch'],model_version=manifest['modelVersion'],versions=versions,gpu=torch.cuda.get_device_name(0),pretrained=False,strict=True,precision='FP32',batch_size=1,cutoff=.5,classes=cfg['class_mapping'],normalization=cfg['normalization'],preprocessing='unchanged training DoorDataset: EXIF -> RGB -> BICUBIC pad224 fill(124,116,104) -> original normalization',gradcam_layer=manifest['gradcamLayer'],automatic_pass=False,backend_model_registered=False)
  print('[E02 GPU READY]',json.dumps(self.metadata,ensure_ascii=False),flush=True)
 # tensor/predict/explain are inherited unchanged. No old Engine initialization or weights are used.
