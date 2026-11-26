"""Recolour previously computed maps; no torch import, model load, inference or sudo."""
import ast,hashlib,html,importlib.metadata,json,shutil,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from PIL import Image,ImageOps

ROOT=Path('/path/to/private/validated-project')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 code=ROOT/'ai_api/cam_methods_20261104';mainout=Path(json.loads((code/'latest.json').read_text())['output']);frozen=json.loads((mainout/'manifest.json').read_text())
 source=code/'run.py';assert sha(source)==frozen['sourceCodeHashes']['run.py']
 nodes=[node for node in ast.parse(source.read_text()).body if isinstance(node,ast.FunctionDef) and node.name in ('colours','render_styles','map_status')]
 ns=dict(np=np,Image=Image,ImageOps=ImageOps,hashlib=hashlib);exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
 out=ROOT/'outputs/door_e02_live/cam_style_only_20261104'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True,exist_ok=False)
 report=dict(scope='display-only preview from saved Grad-CAM; HiResCAM/LayerCAM computation is still awaiting authentication',modelLoaded=False,inferencePerformed=False,modelOrPolicyChanged=False,sourceManifestSHA256=sha(mainout/'manifest.json'),rendererVersions={k:importlib.metadata.version(k) for k in ('numpy','Pillow')},cases=[])
 for sample in frozen['samples']:
  sid=sample['id'];target=out/sid;target.mkdir()
  for filename in ('original.jpg','input224.png'):shutil.copyfile(mainout/sid/filename,target/filename)
  for resolution in ('7','14'):
   reference=sample['sameLayerReference']['new'] if resolution=='7' else sample['new14Reference']
   path=Path(reference.get('rawPath',reference.get('path')));expected=reference.get('rawSHA256',reference.get('sha256'));assert sha(path)==expected
   raw=np.load(path,allow_pickle=False);assert raw.shape==(int(resolution),int(resolution)) and np.isfinite(raw).all()
   fingerprint=hashlib.sha256(raw.tobytes()).hexdigest();folder=target/'new'/resolution/'GradCAM';folder.mkdir(parents=True)
   shutil.copyfile(path,folder/'raw.npy');status=ns['map_status'](raw)
   row=dict(id=sid,resolution=resolution,status=status,rawSourceSHA256=expected,category=sample['source_categories'])
   if status=='GENERATED':row.update(ns['render_styles'](folder,raw,sample['displaySize']))
   assert hashlib.sha256(raw.tobytes()).hexdigest()==fingerprint
   report['cases'].append(row)
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAM 스타일 미리보기</title><style>body{font-family:"Malgun Gothic",sans-serif;max-width:1500px;margin:24px auto;padding:0 20px;background:#f3f6fa;color:#172536;line-height:1.7}header,section{background:white;padding:20px;border-radius:10px;margin-bottom:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}figure{margin:0;border:1px solid #cad5e2;background:#eef3f8}img{width:100%;display:block}figcaption{padding:10px}select{font:inherit;padding:8px}.notice{padding:12px;background:#fff0ce}</style></head><body><header><h1>동일한 CAM · 색상 스타일만 비교</h1><p>모델 재추론 없이 저장된 재학습 도어 모델의 Grad-CAM을 재사용했습니다. 첨부 사진처럼 JET 계열 색상으로 표시하고 겹침 강도를 조절했습니다. 같은 줄의 세 스타일은 원시 맵과 강조 위치가 같습니다.</p><p class="notice">이 페이지는 색상 미리보기입니다. 0맵 원인 점검과 HiResCAM·LayerCAM의 새 계산은 아직 관리자 인증 대기 중입니다. 색상 변경이 실제 결함 위치 정확도의 개선을 뜻하지 않습니다.</p><label>레이어 <select id="layer"><option value="7">현재 7×7</option><option value="14">후보 14×14</option></select></label></header><main id="cases"></main><script>
const data=DATA;
function figure(src,title){return '<figure><a href="'+src+'" target="_blank"><img src="'+src+'"></a><figcaption>'+title+'</figcaption></figure>'}
function draw(){const layer=document.getElementById('layer').value;let result='';for(const row of data.filter(r=>r.resolution===layer)){let images=figure(row.id+'/original.jpg','원본 표시');for(const [style,title] of [['legacy','기존 빨강·파랑 40%'],['jet','JET 계열 50%'],['jet_strong','JET 계열 강조 65%']]){images+=row.files?figure(row.id+'/new/'+layer+'/GradCAM/'+row.files[style],title):'<figure><figcaption>'+title+' / '+row.status+'</figcaption></figure>'}result+='<section data-id="'+row.id+'"><h2>'+row.id+' / '+row.category+'</h2><div class="grid">'+images+'</div></section>'}document.getElementById('cases').innerHTML=result}
document.getElementById('layer').addEventListener('change',draw);draw();
</script></body></html>'''
 page=page.replace('DATA',json.dumps(report['cases'],ensure_ascii=False).replace('<','\\u003c'))
 (out/'preview.html').write_text(page)
 with zipfile.ZipFile(out/'cam_style_preview.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for path in out.rglob('*'):
   if path.is_file() and path.suffix!='.zip':archive.write(path,path.relative_to(out))
 (code/'latest_style_only.json').write_text(json.dumps(dict(output=str(out)),indent=2)+'\n')
 print('STYLE_PREVIEW_COMPLETE',out,flush=True)
 print('NO_MODEL_LOAD_OR_INFERENCE',len(report['cases']),flush=True)

if __name__=='__main__':main()
