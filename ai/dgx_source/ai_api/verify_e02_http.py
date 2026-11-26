"""New e02 model actual GPU/loopback HTTP verification, separate from the legacy API."""
import argparse,base64,hashlib,io,json,math,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
from PIL import Image
from ai_api.e02_engine import CandidateEngine,validate_candidate,ROOT,MANIFEST
from ai_api.e02_service import CandidateService
from ai_api.server import Server,Handler,Downloader
from ai_api import backend_contract
from ai_api.cam_encoding import encode_overlay
from ai_api.verify_gpu import state_hash

def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,default=MANIFEST);args=parser.parse_args();manifest,run,cfg=validate_candidate(args.manifest);out=ROOT/'outputs/door_e02_http'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 report=dict(status='running',scope='actual candidate GPU + same-container loopback HTTP only; no real backend/DB/mobile',modelVersion=manifest['modelVersion'],modelVersionRegistered=False,actualGPU=False,actualHTTP=False,legacyModelOrServiceChanged=False,finalTestRead=False,finalV4Compliance=False,zeroConstantWireContract='pending; existing development fallback, no invented status',pendingProfileTimeDefinition='legacy classification-only timing, not complete handler time',nativeZeroMapObserved=False,nativeConstantMapObserved=False,checks=[],timingDefinition='handler entry/body read through download/decode/queue/classification/CAM/encoding; excludes startup, JSON serialization, network transmission, backend and app',sourceSHA256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.manifest,Path(__file__),ROOT/'ai_api/e02_engine.py',ROOT/'ai_api/e02_service.py']})
 servers=[];started=[];threads=[];dump(out/'report.json',report);print('[E02 HTTP OUTPUT]',out,flush=True)
 try:
  engine=CandidateEngine(args.manifest);report.update(actualGPU=True,model=engine.metadata);initial=state_hash(engine);report['initialGpuAllocatedBytes']=engine.torch.cuda.memory_allocated();samples=manifest['samples'];baseline=[engine.predict(Path(s['image_path'])) for s in samples];blobs={f'/sample/{i}':Path(s['image_path']).read_bytes() for i,s in enumerate(samples)};dump(out/'selection.json',samples)
  for s,b in zip(samples,baseline):
   if b['predicted_class']!=s['predicted_class']:raise AssertionError('Fixed fixture class changed; do not substitute another sample')
   if s['verified_single_score'] is not None and not math.isclose(b['raw_defect_score'],s['verified_single_score'],abs_tol=1e-6,rel_tol=1e-4):raise AssertionError('Verified single score differs')
  class Images(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    path=urlsplit(self.path).path;blob=b'corrupt-image' if path=='/broken' else blobs.get(path);self.send_response(200 if blob is not None else 404);self.send_header('Content-Length',str(len(blob or b'')));self.end_headers();self.wfile.write(blob or b'')
  image_server=ThreadingHTTPServer(('127.0.0.1',0),Images);servers.append(image_server);origin=f'http://127.0.0.1:{image_server.server_port}'
  def launch_api():
   server=Server(('127.0.0.1',0),Handler);servers.append(server);server.service=CandidateService(engine,manifest['modelVersion'],Downloader([origin]),out/'runtime',response_profile=backend_contract.PROFILE,cam_format='jpeg',jpeg_quality=90);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();threads.append(thread);started.append(server);return server
  thread=threading.Thread(target=image_server.serve_forever,daemon=True);thread.start();threads.append(thread);started.append(image_server);api=launch_api();opener=build_opener(ProxyHandler({}));report.update(actualHTTP=True,imageOrigin=origin,apiOrigin=f'http://127.0.0.1:{api.server_port}')
  with opener.open(f'http://127.0.0.1:{api.server_port}/internal/v1/models',timeout=30) as response:
   inventory=json.load(response);assert response.headers['X-AI-Model-SHA256']==manifest['checkpointSHA256']
  assert inventory=={'data':[dict(modelVersion=manifest['modelVersion'],partCode='DOOR',calibratorVersion=None,loadable=True)]};dump(out/'models.json',inventory)
  report_lock=threading.RLock()
  def record_check(check):
   with report_lock:
    position=next((i for i,c in enumerate(report['checks']) if c['case']==check['case']),None)
    if position is None:report['checks'].append(dict(check))
    else:report['checks'][position]=dict(check)
    dump(out/'report.json',report)
  def request(case,index=0,changes=None,expected=200,forced=False,raw=None,expected_format='jpeg'):
   iid=str(uuid.uuid5(uuid.NAMESPACE_URL,out.name+':'+case));body=dict(inspectionId=iid,partCode='DOOR',requestedModelVersion=manifest['modelVersion'],imageUrl=f'{origin}/sample/{index}?sig=local-test');body.update(changes or {});data=raw if raw is not None else json.dumps(body).encode();before=time.perf_counter()
   try:
    with opener.open(Request(f'http://127.0.0.1:{api.server_port}/internal/v1/predict',data=data,headers={'Content-Type':'application/json'}),timeout=300) as response:code=response.status;wire=response.read();headers=dict(response.headers)
   except HTTPError as exc:code=exc.code;wire=exc.read();headers=dict(exc.headers)
   result=json.loads(wire);check=dict(case=case,status=code,inspectionId=iid,forcedBranch=forced,httpRoundtripMs=(time.perf_counter()-before)*1000,responseBytes=len(wire),imageIndex=index);record_check(check);dump(out/(case+'_request.json'),body if raw is None else {'raw':raw.decode()});dump(out/(case+'_response.json'),result);dump(out/(case+'_headers.json'),headers)
   assert code==expected,(case,code)
   if code!=200:
    e=result['error'];assert set(e)=={'inspectionId','code','message','traceId'} and e['traceId']==headers['X-Trace-Id']
    if raw is None:assert e['inspectionId']==iid
    expected_errors={'invalid_json':'INVALID_REQUEST','missing_field':'INVALID_REQUEST','unsupported_part':'UNSUPPORTED_PART','wrong_model':'MODEL_VERSION_MISMATCH','missing_image':'IMAGE_ACCESS_FAILED','broken_image':'INVALID_IMAGE','injected_classification_failure':'INFERENCE_FAILED'}
    assert e['code']==expected_errors[case]
    assert 'PRIVATE' not in json.dumps(result);check['errorCode']=e['code'];record_check(check);print('[E02 CASE]',case,code,flush=True);return result
   assert result['inspectionId']==iid and result['modelVersion']==manifest['modelVersion'] and result['predictedQuality']==('DEFECT' if baseline[index]['predicted_class'] else 'GOOD')
   score=result['rawDefectProbability'];assert isinstance(score,(float,int)) and math.isfinite(score) and 0<=score<=1 and math.isclose(score,baseline[index]['raw_defect_score'],abs_tol=1e-6,rel_tol=1e-4)
   assert result['calibratedDefectProbability'] is None and result['calibratorVersion'] is None
   from PIL import ImageOps
   with Image.open(io.BytesIO(blobs[f'/sample/{index}'])) as im:display=ImageOps.exif_transpose(im).convert('RGB')
   assert (result['imageWidth'],result['imageHeight'])==display.size
   profile=headers['X-AI-Contract-Profile'];check.update(predictedQuality=result['predictedQuality'],rawScore=score,inferenceTimeMs=result['inferenceTimeMs'],contractProfile=profile)
   if profile==backend_contract.PENDING_PROFILE:
    assert result['gradcam']['status'] in ('ZERO_MAP','CONSTANT_MAP') and headers['X-AI-Contract-Pending']=='zero-constant-map-semantics'
    check['camStatus']=result['gradcam']['status']
    if not forced:report['nativeZeroMapObserved' if result['gradcam']['status']=='ZERO_MAP' else 'nativeConstantMapObserved']=True
   else:
    assert profile==backend_contract.PROFILE and isinstance(result['inferenceTimeMs'],int) and result['inferenceTimeMs']>=0
    if result['predictedQuality']=='GOOD' or case=='injected_cam_failure':assert result['gradcam'] is None
    else:
     cam=result['gradcam'];assert set(cam)=={'targetClass','format','imageBase64'} and cam['targetClass']=='DEFECT' and cam['format']==expected_format
     blob=base64.b64decode(cam['imageBase64'],validate=True)
     with Image.open(io.BytesIO(blob)) as im:assert im.size==display.size and im.format==('PNG' if expected_format=='png' else 'JPEG');im.verify()
     (out/(case+'_cam.'+expected_format)).write_bytes(blob);check['camBytes']=len(blob);check['camStatus']='GENERATED'
   record_check(check);print('[E02 CASE]',case,code,flush=True);return result
  request('good_0',0);request('good_1',1)
  with patch.object(api.service,'cam_format','png'):request('reference_png',2,expected_format='png')
  defect=request('defect_jpeg',2);assert defect['gradcam'] is not None and defect['gradcam'].get('format')=='jpeg'
  expected_jpeg,_=encode_overlay((out/'reference_png_cam.png').read_bytes(),(defect['imageWidth'],defect['imageHeight']),'jpeg',90);assert expected_jpeg==base64.b64decode(defect['gradcam']['imageBase64'],validate=True);report['jpegMatchesFreshPNG']=True
  request('stored_defect',3)
  request('invalid_json',raw=b'{broken',expected=400);request('missing_field',changes={'imageUrl':''},expected=400);request('unsupported_part',changes={'partCode':'OTHER'},expected=422);request('wrong_model',changes={'requestedModelVersion':'door-swin-tiny-e20-8d042c7bfab2'},expected=409);request('missing_image',changes={'imageUrl':origin+'/missing'},expected=422);request('broken_image',changes={'imageUrl':origin+'/broken'},expected=422)
  with patch.object(engine,'explain',side_effect=RuntimeError('PRIVATE verifier CAM fault')):request('injected_cam_failure',2,forced=True)
  with patch.object(engine,'predict',side_effect=RuntimeError('PRIVATE verifier classification fault')):request('injected_classification_failure',expected=503,forced=True)
  for name,value in [('zero',0),('constant',1)]:
   with patch.object(engine,'explain',return_value=dict(state_unchanged=True,eval_mode=True,constant=True,raw_min=value,raw_max=value)):
    result=request('injected_'+name,2,forced=True);assert result['gradcam']['status']==('ZERO_MAP' if value==0 else 'CONSTANT_MAP')
  request('after_failure_good',0);request('after_failure_defect',2)
  with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:request('parallel_'+str(i),i%4),range(4)))
  # Recreate only this verification server/service, preserving the same strict-loaded engine.
  api.shutdown();api.server_close();started.remove(api);servers.remove(api);api.service.engine=None;del engine
  engine=CandidateEngine(args.manifest);assert state_hash(engine)==initial
  api=launch_api();request('service_restart_good',0);request('service_restart_defect',2);report['restartScope']='HTTP service and CandidateEngine destroyed/recreated; checkpoint strict-loaded again in same verifier process; OS/container restart not tested'
  expect={c['inspectionId']:samples[c['imageIndex']]['image_sha256'] for c in report['checks'] if c['status']==200 or c['case']=='injected_classification_failure'}
  deadline=time.monotonic()+5
  while True:
   audit=[json.loads(line) for line in (out/'runtime/requests.jsonl').read_text().splitlines()]
   if set(expect)<={row.get('inspectionId') for row in audit if 'imageSha256' in row}:break
   if time.monotonic()>deadline:raise AssertionError('Successful audit records missing')
   threading.Event().wait(.02)
  for row in audit:
   if 'imageSha256' in row and row['inspectionId'] in expect:assert row['imageSha256']==expect[row['inspectionId']]
  report['finalGpuAllocatedBytes']=engine.torch.cuda.memory_allocated();report['gpuAllocationDeltaBytes']=report['finalGpuAllocatedBytes']-report['initialGpuAllocatedBytes'];report['memoryScope']='single test sequence and engine reload only; not a long-running leak certification'
  report.update(auditInspectionPhotoMapping=True,modelStateUnchanged=state_hash(engine)==initial,evalMode=not engine.model.training,checkpointUnchanged=hashlib.sha256((run/'best.pt').read_bytes()).hexdigest()==manifest['checkpointSHA256'])
  assert report['modelStateUnchanged'] and report['evalMode'] and report['checkpointUnchanged'];report['status']='functional_passed_final_contract_and_independence_open';report['backendIntegrationVerified']=False
 except BaseException as exc:report.update(status='failed_or_interrupted',errorType=type(exc).__name__,error=str(exc));raise
 finally:
  for server in reversed(servers):
   if server in started:server.shutdown()
   server.server_close()
  for thread in threads:thread.join(timeout=5)
  dump(out/'report.json',report);print('[E02 HTTP RESULT]',report['status'],flush=True);print('[E02 HTTP REPORT]',out/'report.json',flush=True)
if __name__=='__main__':main()
