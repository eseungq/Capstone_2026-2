"""Live HTTP + GPU verification. No final-test manifest or image is read.

Executed only on the existing validated GPU container. Outputs are new artifacts.
Failure injection is scoped to this test process, never exposed by production API.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from PIL import Image, ImageChops, ImageOps
from ai_api.server import Service, Server, Handler, Downloader
from ai_api import contract

ROOT=Path('/path/to/private/validated-project')
RUN=ROOT/'outputs/training/door_swin_tiny_20261008_183758_369671'


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def state_hash(engine):
    digest=hashlib.sha256()
    for key,value in engine.model.state_dict().items():
        digest.update(key.encode());digest.update(value.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def select_samples(rows, internal, cam_metadata):
    eligible={str(Path(r['image_path']).resolve()):r for r in rows
              if str(Path(r['image_path']).resolve()) in internal}
    good=[r for r in eligible.values() if int(r['predicted_class'])==0][:2]
    recorded=[s for s in cam_metadata['samples'] if s['target_class']==1
              and str(Path(s['image_path']).resolve()) in eligible
              and int(eligible[str(Path(s['image_path']).resolve())]['predicted_class'])==1]
    nonzero=next((s for s in recorded if not s['constant'] and s['raw_max']>0 and s['overlay']),None)
    zero=next((s for s in recorded if s['raw_min']==0 and s['raw_max']==0),None)
    if len(good)!=2 or nonzero is None or zero is None:
        raise RuntimeError('Need internal GOOD x2, recorded DEFECT class-1 nonconstant CAM, and recorded DEFECT zero CAM')
    evidence={str(Path(s['image_path']).resolve()):s for s in (nonzero,zero)}
    samples=good+[eligible[str(Path(s['image_path']).resolve())] for s in (nonzero,zero)]
    selection=[]
    for row in samples:
        old=evidence.get(str(Path(row['image_path']).resolve()))
        selection.append(dict(image_path=row['image_path'],savedPredictedClass=int(row['predicted_class']),
                              purpose='GOOD_no_CAM' if old is None else ('recorded_zero_CAM' if old['constant'] else 'recorded_nonzero_CAM'),
                              priorCam=old))
    return samples,selection


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model-version',required=True)
    args=parser.parse_args()
    output=ROOT/'ai_api/verification'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True)
    report=dict(scope='small internal validation subset, not model performance evaluation or backend integration',
                contractProfile=contract.PROFILE,actualGpuVerified=False,liveHttpVerified=False,
                finalTestUsed=False,modelVersion=args.model_version,modelVersionRegistration='unconfirmed development identifier',
                finalV4Compliance='not_verified',checks=[],examples=[])
    servers=[]
    threads=[]
    saved_score_failures=[]
    try:
        # This is the model-selection INTERNAL validation list. Never open door_test.csv.
        with (ROOT/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig') as stream:
            internal={str(Path(row['image_path']).resolve()) for row in csv.DictReader(stream)}
        with (RUN/'best_internal_validation_predictions.csv').open(encoding='utf-8-sig') as stream:
            rows=list(csv.DictReader(stream))
        cam_path=ROOT/'outputs/evaluation/door_20261015_024950_271668/gradcam/metadata.json'
        samples,selection=select_samples(rows,internal,json.loads(cam_path.read_text()))
        report.update(sampleSelection=selection,priorCamMetadata=str(cam_path))
        dump(output/'sample_selection.json',selection)
        print('[SAMPLES READY] GOOD 2 / recorded nonzero DEFECT 1 / recorded zero DEFECT 1',flush=True)
        images={f'/sample/{i}':Path(row['image_path']).read_bytes() for i,row in enumerate(samples)}
        class Images(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://unapproved.invalid/image');self.end_headers();return
                data=b'corrupt-image' if self.path=='/broken' else images.get(self.path)
                self.send_response(200 if data is not None else 404)
                self.send_header('Content-Length',str(len(data or b'')));self.end_headers();self.wfile.write(data or b'')
        image_server=ThreadingHTTPServer(('127.0.0.1',0),Images)
        servers.append(image_server)
        origin=f'http://127.0.0.1:{image_server.server_port}'
        from prototype.engine import Engine
        engine=Engine()
        original_state=state_hash(engine)
        report['model']=engine.metadata
        api=Server(('127.0.0.1',0),Handler)
        servers.append(api)
        api.service=Service(engine,args.model_version,Downloader([origin]),output/'runtime')
        for server in servers:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();threads.append(thread)
        endpoint=f'http://127.0.0.1:{api.server_port}/internal/v1/predict'
        print(f'[GPU HTTP READY] imageOrigin={origin} api={endpoint} output={output}',flush=True)
        report.update(actualGpuExecuted=True,liveHttpExecuted=True)
        opener=build_opener(ProxyHandler({}))
        def body(i,ident):
            return dict(inspectionId=ident,partCode='DOOR',requestedModelVersion=args.model_version,imageUrl=f'{origin}/sample/{i}')
        def request(payload):
            data=json.dumps(payload).encode()
            try:
                with opener.open(Request(endpoint,data=data,headers={'Content-Type':'application/json'}),timeout=300) as response:
                    return response.status,json.load(response)
            except HTTPError as exc:return exc.code,json.load(exc)
        baselines=[]
        cam_statuses=[]
        cam_bytes={}
        generated=0
        for i,row in enumerate(samples):
            with api.service.model_lock: baseline=engine.predict(Path(row['image_path']))
            baselines.append(baseline)
            status,response=request(body(i,f'gpu-sample-{i}'))
            dump(output/f'sample_{i}_response.json',response)
            assert status==200,response
            assert response['inspectionId']==f'gpu-sample-{i}' and response['modelVersion']==args.model_version
            expected='DEFECT' if baseline['predicted_class'] else 'GOOD'
            assert baseline['predicted_class']==int(row['predicted_class'])
            assert response['predictedQuality']==expected
            assert math.isclose(response['rawDefectProbability'],baseline['raw_defect_score'],abs_tol=1e-6,rel_tol=1e-4)
            saved_match=math.isclose(response['rawDefectProbability'],float(row['raw_defect_score']),abs_tol=1e-6,rel_tol=1e-4)
            if not saved_match:
                saved_score_failures.append(dict(inspectionId=response['inspectionId'],saved=float(row['raw_defect_score']),
                    actual=response['rawDefectProbability'],difference=abs(response['rawDefectProbability']-float(row['raw_defect_score']))))
                print(f'[SAVED SCORE MISMATCH] sample={i}; preserve failure, continue independent CAM checks',flush=True)
            report['savedScoreFailures']=saved_score_failures
            assert response['calibratedDefectProbability'] is None and response['calibratorVersion'] is None
            if baseline['predicted_class']==1: assert response['gradcam']['targetClass']==1
            with Image.open(io.BytesIO(images[f'/sample/{i}'])) as source:
                size=ImageOps.exif_transpose(source).size
            assert (response['imageWidth'],response['imageHeight'])==size
            if expected=='GOOD':
                assert response['gradcam']['status']=='NOT_GENERATED_GOOD' and response['gradcam']['base64'] is None
            elif response['gradcam']['status']=='GENERATED':
                generated+=1
                png=base64.b64decode(response['gradcam']['base64'],validate=True)
                cam_bytes[i]=png
                (output/f'sample_{i}_decoded_cam.png').write_bytes(png)
                with Image.open(io.BytesIO(png)) as decoded:
                    assert decoded.format=='PNG' and decoded.size==size
                    with tempfile.TemporaryDirectory(dir=output) as reference_dir:
                        with api.service.model_lock: info=engine.explain(Path(row['image_path']),Path(reference_dir),1)
                        assert not info['constant']
                        with Image.open(Path(reference_dir)/'cam1.png') as reference:
                            maximum=max(high for low,high in ImageChops.difference(decoded.convert('RGB'),reference.convert('RGB')).getextrema())
                            assert maximum<=1,'Decoded CAM differs from standalone same-image class-1 CAM'
            else: assert response['gradcam']['status'] in ('ZERO_MAP','CONSTANT_MAP')
            report['checks'].append(dict(inspectionId=response['inspectionId'],imageSha256=hashlib.sha256(images[f'/sample/{i}']).hexdigest(),
                baselineScore=baseline['raw_defect_score'],apiScore=response['rawDefectProbability'],absoluteDifference=abs(baseline['raw_defect_score']-response['rawDefectProbability']),
                savedBatch8Score=float(row['raw_defect_score']),camStatus=response['gradcam']['status']))
            report['checks'][-1].update(samplePurpose=selection[i]['purpose'])
            report['checks'][-1].update(savedBatch8ScoreMatches=saved_match)
            cam_statuses.append(response['gradcam']['status'])
            print(f'[SAMPLE OK] index={i} quality={expected} cam={response["gradcam"]["status"]}',flush=True)
            report['examples'].append(dict(file=f'sample_{i}_response.json',source='actual GPU + live HTTP',failureInjection=False))
        assert generated>0,'No nonconstant DEFECT CAM PNG: review zero/constant map evidence separately'
        cases=[('bad_request',{},400,'INVALID_REQUEST'),('unsupported_part',dict(body(0,'bad-part'),partCode='OTHER'),422,'UNSUPPORTED_PART'),
               ('wrong_version',dict(body(0,'bad-version'),requestedModelVersion='unregistered'),409,'MODEL_VERSION_MISMATCH'),
               ('image_missing',dict(body(0,'missing'),imageUrl=origin+'/missing'),422,'IMAGE_ACCESS_FAILED'),
               ('broken_image',dict(body(0,'broken'),imageUrl=origin+'/broken'),422,'INVALID_IMAGE'),
               ('redirect',dict(body(0,'redirect'),imageUrl=origin+'/redirect'),422,'IMAGE_ACCESS_FAILED')]
        for name,payload,expected_status,code in cases:
            status,response=request(payload);assert status==expected_status and response['error']['code']==code
            dump(output/f'{name}_response.json',response)
            report['examples'].append(dict(file=f'{name}_response.json',source='live HTTP negative case',failureInjection=False))
        def parallel(i):
            index=i%len(samples);status,response=request(body(index,f'parallel-{i}'))
            assert status==200 and response['inspectionId']==f'parallel-{i}'
            assert math.isclose(response['rawDefectProbability'],baselines[index]['raw_defect_score'],abs_tol=1e-6,rel_tol=1e-4)
            assert response['predictedQuality']==('DEFECT' if baselines[index]['predicted_class'] else 'GOOD')
            assert response['modelVersion']==args.model_version
            assert response['calibratedDefectProbability'] is None and response['calibratorVersion'] is None
            assert response['gradcam']['status']==cam_statuses[index]
            if baselines[index]['predicted_class']==1: assert response['gradcam']['targetClass']==1
            if baselines[index]['predicted_class']==0:
                assert response['gradcam']['status']=='NOT_GENERATED_GOOD' and response['gradcam']['base64'] is None
            if index in cam_bytes:
                png=base64.b64decode(response['gradcam']['base64'],validate=True)
                with Image.open(io.BytesIO(png)) as decoded, Image.open(io.BytesIO(cam_bytes[index])) as expected_cam:
                    assert decoded.size==expected_cam.size
                    assert max(high for low,high in ImageChops.difference(decoded.convert('RGB'),expected_cam.convert('RGB')).getextrema())<=1
            return dict(inspectionId=response['inspectionId'],imageIndex=index,gradcamStatus=response['gradcam']['status'])
        with ThreadPoolExecutor(max_workers=2) as pool:report['parallelChecks']=list(pool.map(parallel,range(6)))
        # Faults exist only in this verifier's injected wrapper, then restore the actual engine.
        class Fault:
            def __init__(self,mode):self.mode=mode
            def predict(self,path):
                if self.mode=='classification':raise RuntimeError('test-only classification fault')
                return engine.predict(path)
            def explain(self,*args):
                if self.mode=='cam':raise RuntimeError('test-only CAM fault')
                return dict(state_unchanged=True,eval_mode=True,constant=True,raw_min=0,raw_max=0)
        for mode in ('classification','cam','zero'):
            try:
                api.service.engine=Fault(mode)
                status,response=request(body(2,'fault-'+mode))
                if mode=='classification':assert status==503 and response['error']['code']=='INFERENCE_FAILED'
                else:assert status==200 and response['predictedQuality']=='DEFECT' and response['gradcam']['status']==('FAILED' if mode=='cam' else 'ZERO_MAP')
                dump(output/f'injected_{mode}_response.json',response)
                report['examples'].append(dict(file=f'injected_{mode}_response.json',source='test-only injected fault; not model performance',failureInjection=True))
            finally:api.service.engine=engine
        assert state_hash(engine)==original_state and not engine.model.training
        report.update(modelStateUnchanged=True,independentHttpCamChecksPassed=True)
        assert not saved_score_failures,'Saved batch-8 score mismatch; tolerance unchanged; independent HTTP/CAM stages completed'
        report.update(actualGpuVerified=True,liveHttpVerified=True,modelStateUnchanged=True,
                      tolerance=dict(absolute=1e-6,relative=1e-4),result='passed')
    except Exception as exc:
        report.update(result='failed_or_blocked',failureType=type(exc).__name__,failure=str(exc))
        raise
    except KeyboardInterrupt:
        report.update(result='interrupted',failureType='KeyboardInterrupt')
        raise
    finally:
        for server,thread in zip(servers,threads):server.shutdown();thread.join(timeout=5)
        for server in servers:server.server_close()
        dump(output/'verification.json',report)
        print('[VERIFICATION RESULT] '+report.get('result','not_completed'),flush=True)
        print('Verification report:',output/'verification.json',flush=True)


if __name__=='__main__':main()
