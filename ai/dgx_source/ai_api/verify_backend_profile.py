"""Actual GPU/loopback HTTP checks for the opt-in 10/28 partial backend adapter.

Not backend/DB/app integration. Final test images are never read. Fault injection
is restricted to this verifier process; production has no fault switch.
"""
import argparse
import base64
import csv
import io
import json
import math
import hashlib
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler
from PIL import Image
from ai_api import backend_contract
from ai_api.server import Service,Server,Handler,Downloader
from ai_api.cam_encoding import encode_overlay
from ai_api.verify_gpu import ROOT,RUN,select_samples,state_hash,dump


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model-version',required=True)
    parser.add_argument('--cam-format',choices=['png','jpeg'],default='png');parser.add_argument('--jpeg-quality',type=int,default=90);args=parser.parse_args()
    if not 1<=args.jpeg_quality<=95:parser.error('--jpeg-quality must be 1..95')
    out=ROOT/'ai_api/verification'/('backend_profile_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(parents=True)
    report=dict(scope='actual GPU and same-container loopback HTTP; no backend/DB/app integration',profile=backend_contract.PROFILE,actualGpuExecuted=False,actualHttpExecuted=False,finalTestUsed=False,modelVersion=args.model_version,modelVersionRegistered=False,finalV4Compliance=False,zeroConstantMapRule='unresolved; original successful classification and development CAM state retained',checks=[],result='running')
    servers=[];threads=[];started_servers=[]
    report.update(camFormat=args.cam_format,jpegQuality=args.jpeg_quality if args.cam_format=='jpeg' else None)
    print('[BACKEND PROFILE OUTPUT]',out,flush=True)
    try:
        with (ROOT/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig') as f:internal={str(Path(r['image_path']).resolve()) for r in csv.DictReader(f)}
        with (RUN/'best_internal_validation_predictions.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
        samples,selection=select_samples(rows,internal,json.loads((ROOT/'outputs/evaluation/door_20261015_024950_271668/gradcam/metadata.json').read_text()));dump(out/'selection.json',selection)
        images={f'/sample/{i}':Path(r['image_path']).read_bytes() for i,r in enumerate(samples)}
        class Images(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                path=urlsplit(self.path).path;blob=b'corrupt-image' if path=='/broken' else images.get(path)
                self.send_response(200 if blob is not None else 404);self.send_header('Content-Length',str(len(blob or b'')));self.end_headers();self.wfile.write(blob or b'')
        image_server=ThreadingHTTPServer(('127.0.0.1',0),Images);servers.append(image_server);origin=f'http://127.0.0.1:{image_server.server_port}'
        from prototype.engine import Engine,sha
        engine=Engine();report.update(actualGpuExecuted=True,model=engine.metadata);initial=state_hash(engine)
        baseline=[engine.predict(Path(r['image_path'])) for r in samples]
        api=Server(('127.0.0.1',0),Handler);servers.append(api);api.service=Service(engine,args.model_version,Downloader([origin]),out/'runtime',response_profile=backend_contract.PROFILE,cam_format=args.cam_format,jpeg_quality=args.jpeg_quality)
        for server in servers:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();threads.append(thread);started_servers.append(server)
        endpoint=f'http://127.0.0.1:{api.server_port}';opener=build_opener(ProxyHandler({}))
        with opener.open(endpoint+'/internal/v1/models',timeout=30) as response:
            inventory=json.load(response);inventory_headers=dict(response.headers)
            if response.headers.get('X-AI-Model-SHA256')!=engine.metadata['model_sha256']:raise AssertionError('Inventory checksum mismatch')
        dump(out/'models.json',inventory);entry=inventory['data'][0]
        assert entry==dict(modelVersion=args.model_version,partCode='DOOR',calibratorVersion=None,loadable=True)
        report['actualHttpExecuted']=True
        def request(case,index=0,changes=None,expected_status=200,injected=False):
            iid=str(uuid.uuid5(uuid.NAMESPACE_URL,out.name+':'+case));body=dict(inspectionId=iid,partCode='DOOR',requestedModelVersion=args.model_version,imageUrl=f'{origin}/sample/{index}?exp=fixture&sig=fixture')
            if changes:body.update(changes)
            started=time.perf_counter()
            try:
                with opener.open(Request(endpoint+'/internal/v1/predict',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=300) as response:status=response.status;result=json.load(response);headers=dict(response.headers)
            except HTTPError as exc:status=exc.code;result=json.load(exc);headers=dict(exc.headers)
            elapsed=(time.perf_counter()-started)*1000
            dump(out/(case+'_request.json'),body);dump(out/(case+'_response.json'),result);dump(out/(case+'_headers.json'),headers)
            check=dict(case=case,status=status,inspectionId=iid,forcedFault=injected,httpRoundtripMs=elapsed,source='fresh actual GPU/HTTP' if not injected else 'fresh HTTP with verifier-only forced branch')
            report['checks'].append(check)
            assert status==expected_status,(case,status)
            if status!=200:
                e=result['error'];assert set(e)=={'code','message','traceId','inspectionId'} and e['inspectionId']==iid and e['traceId']==headers['X-Trace-Id']
                return result
            assert result['inspectionId']==iid and result['modelVersion']==args.model_version
            assert result['calibratedDefectProbability'] is None and result['calibratorVersion'] is None
            assert result['predictedQuality']==('DEFECT' if baseline[index]['predicted_class'] else 'GOOD')
            assert math.isclose(result['rawDefectProbability'],baseline[index]['raw_defect_score'],abs_tol=1e-6,rel_tol=1e-4)
            check.update(rawScore=result['rawDefectProbability'],singleBaselineScore=baseline[index]['raw_defect_score'],predictedQuality=result['predictedQuality'],wireProfile=headers['X-AI-Contract-Profile'],wireInferenceTimeMs=result['inferenceTimeMs'])
            if headers['X-AI-Contract-Profile']==backend_contract.PENDING_PROFILE:
                assert result['gradcam']['status'] in ('ZERO_MAP','CONSTANT_MAP') and headers['X-AI-Contract-Pending']=='zero-constant-map-semantics'
                check['backendCompatibleKnownCase']=False
            else:
                assert headers['X-AI-Contract-Profile']==backend_contract.PROFILE
                assert isinstance(result['inferenceTimeMs'],int) and result['inferenceTimeMs']>=0
                check['backendCompatibleKnownCase']=True
                if result['predictedQuality']=='GOOD' or case=='injected_cam_failure':assert result['gradcam'] is None
                else:
                    expected_format='png' if case=='reference_png' else args.cam_format
                    cam=result['gradcam'];assert set(cam)=={'targetClass','format','imageBase64'} and cam['targetClass']=='DEFECT' and cam['format']==expected_format
                    png=base64.b64decode(cam['imageBase64'],validate=True)
                    with Image.open(io.BytesIO(png)) as image:assert image.format==('PNG' if expected_format=='png' else 'JPEG') and image.size==(result['imageWidth'],result['imageHeight']);image.verify()
                    (out/(case+'_cam.'+expected_format)).write_bytes(png);check['camBytes']=len(png);check['camFormat']=expected_format
            print('[BACKEND CASE]',case,status,flush=True)
            return result
        request('good',0)
        if args.cam_format=='jpeg':
            with patch.object(api.service,'cam_format','png'):request('reference_png',2)
        defect=request('defect_nonzero',2)
        if args.cam_format=='jpeg':
            reference=(out/'reference_png_cam.png').read_bytes()
            expected,_=encode_overlay(reference,(defect['imageWidth'],defect['imageHeight']),'jpeg',args.jpeg_quality)
            assert expected==base64.b64decode(defect['gradcam']['imageBase64'],validate=True)
            report['jpegMatchesFreshPNGEncoding']=True
            report['freshPNGReferenceSHA256']=hashlib.sha256(reference).hexdigest()
        zero=request('actual_zero',3)
        assert zero['gradcam']['status']=='ZERO_MAP'
        request('unsupported_part',changes={'partCode':'OTHER'},expected_status=422)
        request('wrong_model_version',changes={'requestedModelVersion':'not-registered'},expected_status=409)
        request('image_missing',changes={'imageUrl':origin+'/missing'},expected_status=422)
        request('corrupt_image',changes={'imageUrl':origin+'/broken'},expected_status=422)
        with patch.object(engine,'explain',side_effect=RuntimeError('verifier-only CAM failure')):request('injected_cam_failure',2,injected=True)
        with patch.object(engine,'predict',side_effect=RuntimeError('verifier-only classification failure')):request('injected_classification_failure',expected_status=503,injected=True)
        request('after_failure_good',0)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda i:request('parallel_'+str(i),0 if i%2==0 else 2),range(4)))
        if state_hash(engine)!=initial or engine.model.training:raise AssertionError('Model state changed')
        assert sha(RUN/'best.pt')==engine.metadata['model_sha256']
        report.update(modelStateUnchanged=True,classificationVsSingleBaseline='passed abs=1e-6 rel=1e-4; not a saved-batch tolerance change',savedBatchDifference='existing issue not reclassified as resolved by this verifier',result='known_cases_passed_zero_contract_open',backendIntegrationVerified=False)
    except BaseException as exc:
        report.update(result='failed_or_interrupted',failureType=type(exc).__name__,failure=str(exc));raise
    finally:
        for server in reversed(servers):
            if server in started_servers:server.shutdown()
            server.server_close()
        for thread in threads:thread.join(timeout=5)
        dump(out/'verification.json',report);print('[BACKEND PROFILE RESULT]',report['result'],flush=True);print('[BACKEND PROFILE REPORT]',out/'verification.json',flush=True)

if __name__=='__main__':main()
