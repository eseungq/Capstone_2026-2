"""Versioned DOOR functional HTTP/restart verification; strict score warnings stay separate.

Legacy verifier remains unchanged and its strict failure is preserved. No model,
precision, preprocessing, threshold or final-test use changes. Host GPU only.
"""
import argparse
import base64
import csv
import gc
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from ai_api.verify_gpu import ROOT,RUN,dump,state_hash
from ai_api import contract
from ai_api.server import Service,Server,Handler,Downloader


def select_development_rows():
    from ai_api.verify_gpu import select_samples
    internal={str(Path(r['image_path']).resolve()) for r in csv.DictReader((ROOT/'outputs/manifests/door_internal_validation.csv').read_text(encoding='utf-8-sig').splitlines())}
    rows=list(csv.DictReader((RUN/'best_internal_validation_predictions.csv').read_text(encoding='utf-8-sig').splitlines()))
    if len(internal)!=2039 or {str(Path(r['image_path']).resolve()) for r in rows}!=internal:raise ValueError('Internal source mismatch')
    old=json.loads((ROOT/'outputs/evaluation/door_20261015_024950_271668/gradcam/metadata.json').read_text())
    base,_=select_samples(rows,internal,old)
    selected={r['image_path']:r for r in base}
    for r in sorted(rows,key=lambda r:(abs(float(r['raw_defect_score'])-.5),r['image_path']))[:4]:selected[r['image_path']]=r
    return rows,list(selected.values()),base


def inspection_id_for(run_name,case_label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'door-development-verification:'+run_name+':'+case_label))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model-version',required=True);args=parser.parse_args()
    from datetime import datetime,timezone
    out=ROOT/'ai_api/verification'/('integration_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(parents=True)
    report={'scope':'DOOR internal-development functional HTTP and real child-process restart; not backend/DB/mobile integration','startedAt':datetime.now(timezone.utc).isoformat(),'result':'running','modelVersion':args.model_version,'contractProfile':contract.PROFILE,'finalV4Compliance':'not_verified','finalTestUsed':False,'freshGpuExecuted':False,'freshHttpExecuted':False,'strictTolerance':{'absolute':1e-6,'relative':1e-4},'legacyVerifier':None,'scoreChecks':[],'restartChecks':[],'httpChecks':[],'failures':[]}
    dump(out/'integration.json',report);print('[INTEGRATION OUTPUT]',out,flush=True)
    servers=[];threads=[];children=[];logs=[]
    try:
        # Run unchanged original verifier. A saved-batch strict failure is recorded, never turned into passed.
        before=set((ROOT/'ai_api/verification').glob('20*/verification.json'));legacy_exception=None
        from ai_api import verify_gpu
        argv=sys.argv[:]
        try:
            sys.argv=['ai_api.verify_gpu','--model-version',args.model_version]
            try:verify_gpu.main()
            except Exception as exc:legacy_exception=type(exc).__name__
        finally:sys.argv=argv
        added=set((ROOT/'ai_api/verification').glob('20*/verification.json'))-before
        if len(added)!=1:raise RuntimeError('Legacy verification output ambiguous')
        legacy_path=added.pop();legacy=json.loads(legacy_path.read_text())
        report['legacyVerifier']={'report':str(legacy_path),'result':legacy.get('result'),'exception':legacy_exception,'savedScoreFailures':legacy.get('savedScoreFailures',[])}
        allowed_saved_failure=(legacy.get('failureType')=='AssertionError' and str(legacy.get('failure','')).startswith('Saved batch-8 score mismatch') and bool(legacy.get('savedScoreFailures')))
        if not legacy.get('independentHttpCamChecksPassed') or (legacy_exception and not allowed_saved_failure):raise RuntimeError('Functional legacy stages did not pass')
        report.update(freshGpuExecuted=True,freshHttpExecuted=True)
        import torch
        from prototype.engine import Engine,sha
        gc.collect();torch.cuda.empty_cache()
        rows,samples,base=select_development_rows();dump(out/'internal_development_samples.json',samples)
        engine=Engine();report['model']=engine.metadata;initial=state_hash(engine)
        report['numericalSettings']={'float32MatmulPrecision':torch.get_float32_matmul_precision(),'cudaMatmulAllowTF32':torch.backends.cuda.matmul.allow_tf32,'cudnnAllowTF32':torch.backends.cudnn.allow_tf32,'cudnnBenchmark':torch.backends.cudnn.benchmark,'cudnnDeterministic':torch.backends.cudnn.deterministic,'modifiedByVerifier':False}
        positions={r['image_path']:i for i,r in enumerate(rows)}
        for r in samples:
            path=Path(r['image_path']);single_tensor=engine.tensor(path);single=engine.predict(path);position=positions[r['image_path']];start=position//8*8;batch=torch.stack([engine.tensor(Path(x['image_path'])) for x in rows[start:start+8]])
            index=position-start;identical=torch.equal(single_tensor,batch[index]);a=hashlib.sha256(single_tensor.contiguous().numpy().tobytes()).hexdigest();b=hashlib.sha256(batch[index].contiguous().numpy().tobytes()).hexdigest()
            with torch.inference_mode():score=float(torch.softmax(engine.model(batch.cuda()),dim=1)[index,1])
            saved=float(r['raw_defect_score']);batch_match=math.isclose(score,saved,abs_tol=1e-6,rel_tol=1e-4);class_match=single['predicted_class']==int(r['predicted_class'])
            check={'imageSha256':sha(path),'imagePath':str(path),'savedBatch8':saved,'recreatedBatch8':score,'single':single['raw_defect_score'],'inputTensorHashBatch1':a,'inputTensorHashBatch8':b,'inputTensorsEqual':identical,'savedBatch8StrictMatch':batch_match,'singleVsSavedBatch8StrictMatch':math.isclose(single['raw_defect_score'],saved,abs_tol=1e-6,rel_tol=1e-4),'classMatchesSaved':class_match,'savedCutoffDistance':abs(saved-.5),'singleCutoffDistance':abs(single['raw_defect_score']-.5)}
            report['scoreChecks'].append(check);dump(out/'integration.json',report)
            if not identical or not batch_match or not class_match:report['failures'].append({'stage':'score_reproduction','imageSha256':check['imageSha256']})
            del batch,single_tensor
        if state_hash(engine)!=initial or engine.model.training:raise RuntimeError('State changed')
        report['scoreModelStateUnchanged']=True
        good=Path(base[0]['image_path']).read_bytes();defect=Path(base[2]['image_path']).read_bytes();images={'/good':good,'/defect':defect}
        class Images(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                blob=images.get(self.path);self.send_response(200 if blob else 404);self.send_header('Content-Length',str(len(blob or b'')));self.end_headers();self.wfile.write(blob or b'')
        image_server=ThreadingHTTPServer(('127.0.0.1',0),Images);servers.append(image_server);thread=threading.Thread(target=image_server.serve_forever,daemon=True);thread.start();threads.append(thread);origin=f'http://127.0.0.1:{image_server.server_port}'
        opener=build_opener(ProxyHandler({}));elapsed=[]
        def post(endpoint,kind,ident):
            payload={'inspectionId':inspection_id_for(out.name,ident),'partCode':'DOOR','requestedModelVersion':args.model_version,'imageUrl':origin+'/'+kind};started=time.perf_counter()
            try:
                with opener.open(Request(endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=300) as response:status=response.status;body=json.load(response)
            except HTTPError as exc:status=exc.code;body=json.load(exc)
            ms=(time.perf_counter()-started)*1000
            if not ident.startswith('injected-'):elapsed.append(ms)
            dump(out/(ident+'_request.json'),payload);dump(out/(ident+'_response.json'),body);report['httpChecks'].append({'inspectionId':payload['inspectionId'],'caseLabel':ident,'status':status,'requestTotalMs':ms,'classificationMs':body.get('inferenceTimeMs'),'responseJsonBytes':len(json.dumps(body).encode()),'predictedQuality':body.get('predictedQuality'),'gradcamStatus':body.get('gradcam',{}).get('status'),'source':'fresh actual HTTP','forcedFault':ident.startswith('injected-')})
            if status==200 and body.get('inspectionId')!=payload['inspectionId']:raise RuntimeError('HTTP request/response inspectionId mismatch')
            return status,body
        # Additional constant-map/failure recovery branch, only injected into this local test instance.
        api=Server(('127.0.0.1',0),Handler);servers.append(api);api.service=Service(engine,args.model_version,Downloader([origin]),out/'runtime');thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start();threads.append(thread);endpoint=f'http://127.0.0.1:{api.server_port}/internal/v1/predict'
        class ConstantFault:
            def predict(self,path):return engine.predict(path)
            def explain(self,*args):return {'state_unchanged':True,'eval_mode':True,'constant':True,'raw_min':1.0,'raw_max':1.0}
        try:
            api.service.engine=ConstantFault();status,body=post(endpoint,'defect','injected-constant')
            if status!=200 or body['predictedQuality']!='DEFECT' or body['gradcam']['status']!='CONSTANT_MAP':raise RuntimeError('Constant-map classification not preserved')
        finally:api.service.engine=engine
        status,body=post(endpoint,'good','after-fault-good')
        if status!=200 or body['predictedQuality']!='GOOD':raise RuntimeError('Failure recovery check failed')
        api.shutdown();threads.pop().join(timeout=5);servers.pop().server_close();api.service.engine=None;del api;del engine;gc.collect();torch.cuda.empty_cache()
        # Actual separate CLI server processes: terminate first, load same model/settings in next.
        previous_good=None
        for generation in [1,2]:
            folder=out/f'restart_{generation}';folder.mkdir();ready=folder/'ready.json';log=(folder/'server.log').open('w');logs.append(log)
            cmd=[sys.executable,'-u','-m','ai_api.server','--development-contract','--model-version',args.model_version,'--image-origin',origin,'--host','127.0.0.1','--port','0','--runtime',str(folder/'runtime'),'--ready-file',str(ready)]
            child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT);children.append(child);deadline=time.monotonic()+180
            print('[RESTART START]',generation,'pid',child.pid,flush=True)
            while not ready.exists():
                if child.poll() is not None:raise RuntimeError('Child startup failed; inspect server.log')
                if time.monotonic()>deadline:raise RuntimeError('Child startup readiness deadline exceeded')
                time.sleep(.2)
            info=json.loads(ready.read_text())
            if not info['ready'] or info['pid']!=child.pid or info['modelSha256']!=report['model']['model_sha256']:raise RuntimeError('Readiness/model mismatch')
            baseurl=f"http://127.0.0.1:{info['port']}"
            with opener.open(baseurl+'/internal/v1/models',timeout=30) as response:inventory=json.load(response)
            dump(folder/'models.json',inventory)
            entry=inventory['models'][0]
            if entry['partCode']!='DOOR' or entry['modelVersion']!=args.model_version or not entry['available']:raise RuntimeError('Model inventory readiness differs')
            for kind in ['good','defect']:
                status,body=post(baseurl+'/internal/v1/predict',kind,f'restart-{generation}-{kind}')
                if status!=200 or body['inspectionId']!=inspection_id_for(out.name,f'restart-{generation}-{kind}') or body['modelVersion']!=args.model_version:raise RuntimeError('Restart response differs')
                if body['calibratedDefectProbability'] is not None or body['calibratorVersion'] is not None:raise RuntimeError('Calibration changed')
                if kind=='good':
                    if body['predictedQuality']!='GOOD' or body['gradcam']['status']!='NOT_GENERATED_GOOD':raise RuntimeError('GOOD restart differs')
                    if previous_good is not None and not math.isclose(previous_good,body['rawDefectProbability'],abs_tol=1e-6,rel_tol=1e-4):raise RuntimeError('Restart score differs')
                    previous_good=body['rawDefectProbability']
                else:
                    if body['predictedQuality']!='DEFECT' or body['gradcam']['status']!='GENERATED':raise RuntimeError('Nonzero DEFECT restart differs')
                    from PIL import Image,ImageOps,ImageChops
                    png=base64.b64decode(body['gradcam']['base64'],validate=True);(folder/'decoded_cam.png').write_bytes(png)
                    reference=legacy_path.parent/'sample_2_decoded_cam.png'
                    with Image.open(io.BytesIO(png)) as decoded,Image.open(reference) as previous:
                        if decoded.format!='PNG' or decoded.size!=(body['imageWidth'],body['imageHeight']):raise RuntimeError('Restart PNG invalid')
                        if max(high for low,high in ImageChops.difference(decoded.convert('RGB'),previous.convert('RGB')).getextrema())>1:raise RuntimeError('Restart CAM/image correspondence differs')
            child.terminate();child.wait(timeout=30);stopped=json.loads(ready.read_text())
            if child.returncode!=0 or stopped['ready']:raise RuntimeError('Child graceful shutdown failed')
            report['restartChecks'].append({'generation':generation,'pid':child.pid,'startup':info,'shutdown':stopped,'exitCode':child.returncode,'realProcessRestart':True});dump(out/'integration.json',report)
        strict=[c for c in report['scoreChecks'] if not c['singleVsSavedBatch8StrictMatch']]
        report['singleVsSavedStrictMismatches']=len(strict);report['singleVsSavedMaxAbsoluteDifference']=max(abs(c['single']-c['savedBatch8']) for c in report['scoreChecks'])
        ordered=sorted(elapsed);report['httpTiming']={'n':len(ordered),'p50Ms':statistics.median(ordered),'p95NearestRankMs':ordered[math.ceil(.95*len(ordered))-1],'scope':'local image download + lock wait + decode/classification + CAM + base64/JSON + HTTP receipt/parse; excludes model startup, backend/DB/mobile','notProductionLatencySLA':True}
        report['httpTiming']['byQuality']={quality:{'n':len(values),'p50Ms':statistics.median(values),'p95NearestRankMs':sorted(values)[math.ceil(.95*len(values))-1]} for quality in ['GOOD','DEFECT'] if (values:=[c['requestTotalMs'] for c in report['httpChecks'] if not c['forcedFault'] and c['predictedQuality']==quality])}
        report['tenSecondGoal']='not used as execution timeout; per-call timing retained for goal comparison'
        report['functionalHttpRestartResult']='passed' if not report['failures'] else 'failed'
        report['savedBatchSizeDifferenceResolved']=False
        report['savedBatchSizeDifferenceScope']='Fresh small sample plus preserved historical strict failures; full 2039-image batch1 boundary impact not verified'
        report['result']='functional_passed_saved_score_difference_open' if not report['failures'] and (strict or legacy.get('savedScoreFailures')) else 'functional_passed_full_batch_scope_unverified' if not report['failures'] else 'failed'
        report['finalV4Compliance']='not_verified_pending_contract_placement_and_zero_map_rule'
        if report['failures']:raise RuntimeError('Functional reproduction failed; see integration.json')
    except BaseException as exc:
        report['result']='failed_or_blocked';report['failureType']=type(exc).__name__;report['failure']=str(exc);raise
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=30)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        for log in logs:log.close()
        for server,thread in zip(servers,threads):server.shutdown();thread.join(timeout=5);server.server_close()
        dump(out/'integration.json',report);print('[DOOR INTEGRATION RESULT]',report['result'],flush=True);print('[DOOR INTEGRATION REPORT]',out/'integration.json',flush=True)

if __name__=='__main__':main()
