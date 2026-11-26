"""Freeze model inputs and public equation references for a CPU-only CAM diagnostic."""
import ast, hashlib, json, shutil, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path('/path/to/private/validated-project')
REFERENCES={
 'grad_cam.py':'https://raw.githubusercontent.com/jacobgil/pytorch-grad-cam/master/pytorch_grad_cam/grad_cam.py',
 'hirescam.py':'https://raw.githubusercontent.com/jacobgil/pytorch-grad-cam/master/pytorch_grad_cam/hirescam.py',
 'layer_cam.py':'https://raw.githubusercontent.com/jacobgil/pytorch-grad-cam/master/pytorch_grad_cam/layer_cam.py',
 'LICENSE':'https://raw.githubusercontent.com/jacobgil/pytorch-grad-cam/master/LICENSE',
}

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def main():
 code=ROOT/'ai_api/cam_methods_20261104'
 previous=Path(json.loads((ROOT/'ai_api/cam_model_comparison_20261104/latest.json').read_text())['output'])
 base=json.loads((previous/'comparison_manifest.json').read_text())
 baseline=json.loads((previous/'report.json').read_text())
 assert baseline['status'].startswith('completed')
 for name in ('old','new'):
  run=Path(base['modelRuns'][name]);assert sha(run/'best.pt')==base['modelHashes'][name]
  assert sha(run/'run_config.json')==base['configHashes'][name]
 assert sha(Path(base['datasetSource']))==base['datasetSourceSHA256']
 out=ROOT/'outputs/door_e02_live/cam_methods_20261104'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True,exist_ok=False)
 references={};ref_folder=out/'reference_sources';ref_folder.mkdir()
 for name,url in REFERENCES.items():
  with urllib.request.urlopen(url,timeout=25) as response:data=response.read()
  path=ref_folder/name;path.write_bytes(data)
  if name.endswith('.py'):ast.parse(data.decode('utf-8'))
  references[name]=dict(url=url,path=str(path),sha256=sha(path))
 for sample in base['samples']:
  sid=sample['id'];target=out/sid;target.mkdir()
  assert sha(Path(sample['image_path']))==sample['imageSHA256']
  for name in ('original.jpg','input224.png'):shutil.copyfile(previous/sid/name,target/name)
  sample['sameLayerReference']={name:dict(score=baseline['samples'][sid]['results'][name]['baseline']['probability'],rawPath=str(previous/sid/(name+'_raw.npy')),rawSHA256=sha(previous/sid/(name+'_raw.npy'))) for name in ('old','new')}
  candidate=Path(sample['newCPURawReference']).with_name('candidate_raw.npy')
  sample['new14Reference']=dict(path=str(candidate),sha256=sha(candidate))
 base.update(schema='cam-methods-and-style-fixed-diagnostic-v1',output=str(out),previousComparison=str(previous),references=references,layers=['layers.3.blocks.1.norm1','layers.2.blocks.5.norm1'],methods=['GradCAM','HiResCAM','LayerCAM'],styleConfigurations=dict(legacy=dict(palette='red-blue',alpha=.4),jet=dict(palette='JET-family analytic RGB lookup',alpha=.5),jet_strong=dict(palette='JET-family analytic RGB lookup',alpha=.65)),equationReferenceTolerance=dict(atol=1e-7,rtol=1e-4),referenceScope='Only the published get_cam_weights/get_cam_image equations are executed from frozen source AST; the grad-cam package is not installed or run end-to-end.',newTrainingPerformed=False,productionChanged=False)
 base['previousComparisonSourceCodeHashes']=base.pop('sourceCodeHashes')
 base['sourceCodeHashes']={name:sha(code/name) for name in ('run.py','launch.py','run.sh','prepare.py')}
 paths=[Path(base['datasetSource'])]+[Path(v['path']) for v in references.values()]
 paths += [Path(s['image_path']) for s in base['samples']]
 assert all(p.is_relative_to(ROOT) for p in paths)
 (out/'manifest.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n')
 (code/'latest.json').write_text(json.dumps(dict(output=str(out),manifestSHA256=sha(out/'manifest.json')),indent=2)+'\n')
 print('METHODS_PREPARED',out,flush=True)
 print('FROZEN_REFERENCE_FILES',len(references),'PHOTOS',len(base['samples']),flush=True)

if __name__=='__main__':main()
