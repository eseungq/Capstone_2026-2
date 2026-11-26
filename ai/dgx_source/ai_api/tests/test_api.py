"""HTTP handler tests with injected fixtures, NEVER actual GPU model validation."""
import base64
import csv
import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageOps
from ai_api.server import Service, Handler, Downloader, contract


def picture(value,exif=False):
    image=Image.new('RGB',(20,10),(value,20,30));stream=io.BytesIO()
    orientation=Image.Exif()
    if exif: orientation[274]=6
    image.save(stream,format='PNG' if not exif else 'JPEG',exif=orientation)
    return stream.getvalue()


class FixtureEngine:
    """Test-only injectable engine. There is no production switch selecting this class."""
    mode='normal'
    def __init__(self): self.active=False;self.overlaps=0;self.cam_calls=0
    def enter(self):
        if self.active:self.overlaps+=1
        self.active=True;time.sleep(.005)
    def predict(self,path):
        self.enter()
        try:
            if self.mode=='inference-fail':raise RuntimeError('PRIVATE DETAIL')
            with Image.open(path) as image: score=.9 if image.convert('RGB').getpixel((0,0))[0]>100 else .1
            if self.mode=='nan':score=float('nan')
            return dict(predicted_class=int(score>=.5),raw_defect_score=score,processing_ms=1.0)
        finally:self.active=False
    def explain(self,path,dest,cls):
        assert cls==1
        self.enter();self.cam_calls+=1
        try:
            if self.mode=='cam-fail':raise RuntimeError('PRIVATE CAM DETAIL')
            with Image.open(path) as image: original=ImageOps.exif_transpose(image).convert('RGB')
            original.save(dest/'cam1.png')
            return dict(state_unchanged=True,eval_mode=True,constant=self.mode in ('zero','constant'),
                        raw_min=0 if self.mode!='constant' else 1,raw_max=0 if self.mode=='zero' else 1)
        finally:self.active=False


def memory_request(service,body,raw=False,headers=None,path='/internal/v1/predict'):
    data=body if raw else json.dumps(body).encode()
    h={'Content-Type':'application/json','Content-Length':str(len(data)), 'Connection':'close'}
    if headers:h.update(headers)
    wire=(f'POST {path} HTTP/1.0\r\n'+''.join(f'{k}: {v}\r\n' for k,v in h.items())+'\r\n').encode()+data
    class Connection:
        def __init__(self):self.output=bytearray()
        def makefile(self,*args):return io.BytesIO(wire)
        def sendall(self,data):self.output.extend(data)
        def settimeout(self,*args):pass
    connection=Connection()
    Handler(connection,('127.0.0.1',0),SimpleNamespace(service=service))
    head,payload=bytes(connection.output).split(b'\r\n\r\n',1)
    return int(head.split(b' ')[1]),json.loads(payload)


class API(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=FixtureEngine()
        self.blobs={'http://fixture/good':picture(10,True),'http://fixture/defect':picture(200,True),'http://fixture/broken':b'broken'}
        def download(url):
            if url not in self.blobs:raise contract.Failure('IMAGE_ACCESS_FAILED',422)
            return self.blobs[url]
        self.service=Service(self.engine,'TEST_FIXTURE_NOT_GPU',download,self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def body(self,kind='good',ident='id-1'):
        return dict(inspectionId=ident,partCode='DOOR',requestedModelVersion='TEST_FIXTURE_NOT_GPU',imageUrl='http://fixture/'+kind)
    def test_good_and_defect_png_exif(self):
        good=memory_request(self.service,self.body())[1]
        self.assertEqual(good['predictedQuality'],'GOOD')
        self.assertEqual(good['gradcam']['status'],'NOT_GENERATED_GOOD');self.assertEqual(self.engine.cam_calls,0)
        self.assertIsNone(good['calibratedDefectProbability']);self.assertIsNone(good['calibratorVersion'])
        code,defect=memory_request(self.service,self.body('defect'))
        self.assertEqual(code,200);self.assertEqual(defect['gradcam']['status'],'GENERATED')
        with Image.open(io.BytesIO(base64.b64decode(defect['gradcam']['base64'],validate=True))) as png:
            self.assertEqual(png.size,(10,20));self.assertEqual(png.format,'PNG')
            with Image.open(io.BytesIO(self.blobs['http://fixture/defect'])) as source:
                self.assertEqual(png.tobytes(),ImageOps.exif_transpose(source).convert('RGB').tobytes())
    def test_error_branches_and_no_private_exception(self):
        cases=[({},400,'INVALID_REQUEST'),(dict(self.body(),partCode='OTHER'),422,'UNSUPPORTED_PART'),
               (dict(self.body(),requestedModelVersion='unknown'),409,'MODEL_VERSION_MISMATCH'),
               (self.body('missing'),422,'IMAGE_ACCESS_FAILED'),(self.body('broken'),422,'INVALID_IMAGE')]
        for body,status,error in cases:
            code,result=memory_request(self.service,body)
            self.assertEqual(code,status);self.assertEqual(result['error']['code'],error)
        for mode in ['inference-fail','nan']:
            self.engine.mode=mode
            code,result=memory_request(self.service,self.body())
            self.assertEqual(code,503);self.assertEqual(result['error']['code'],'INFERENCE_FAILED')
            self.assertNotIn('PRIVATE',json.dumps(result))
        self.service.engine=None
        self.assertEqual(memory_request(self.service,self.body())[1]['error']['code'],'MODEL_UNAVAILABLE')
    def test_cam_fail_zero_constant_preserve_prediction(self):
        for mode,status in [('cam-fail','FAILED'),('zero','ZERO_MAP'),('constant','CONSTANT_MAP')]:
            self.engine.mode=mode
            code,result=memory_request(self.service,self.body('defect'))
            self.assertEqual(code,200);self.assertEqual(result['predictedQuality'],'DEFECT')
            self.assertEqual(result['gradcam']['status'],status);self.assertIsNone(result['gradcam']['base64'])
    def test_sequential_parallel_requests_and_audit_identity(self):
        def run(i):
            kind='good' if i%2==0 else 'defect'
            code,result=memory_request(self.service,self.body(kind,str(i)))
            self.assertEqual(code,200);self.assertEqual(result['inspectionId'],str(i))
            self.assertEqual(result['predictedQuality'],'GOOD' if i%2==0 else 'DEFECT')
        for i in range(4):run(i)
        with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(run,range(4,10)))
        self.assertEqual(self.engine.overlaps,0)
        logs=[json.loads(line) for line in (Path(self.temp.name)/'requests.jsonl').read_text().splitlines()]
        self.assertEqual(len(logs),10);self.assertEqual(len({r['requestId'] for r in logs}),10)
        self.assertEqual({r['inspectionId'] for r in logs},{str(i) for i in range(10)})
        self.assertFalse(any(p.is_dir() for p in Path(self.temp.name).iterdir()))
    def test_bad_json_duplicates_content_type_and_paths(self):
        for blob in [b'[]',b'{',b'{"inspectionId":"a","inspectionId":"b"}',b'NaN']:
            self.assertEqual(memory_request(self.service,blob,raw=True)[0],400)
        self.assertEqual(memory_request(self.service,self.body(),headers={'Content-Type':'text/plain'})[0],400)
        self.assertEqual(memory_request(self.service,self.body(),path='/other')[0],404)
    def test_busy(self):
        for _ in range(4):self.service.slots.acquire()
        try:self.assertEqual(memory_request(self.service,self.body())[1]['error']['code'],'BUSY')
        finally:
            for _ in range(4):self.service.slots.release()
    def test_real_internal_image_decode_without_gpu_prediction(self):
        root=Path('/path/to/private/validated-project')
        with (root/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig') as stream:
            path=Path(next(csv.DictReader(stream))['image_path'])
        blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
        self.blobs['http://fixture/actual-internal']=blob
        self.engine.mode='inference-fail'  # Explicit fault: no model performance claim.
        code,response=memory_request(self.service,self.body('actual-internal','actual-image-decode-only'))
        self.assertEqual(code,503);self.assertEqual(response['error']['code'],'INFERENCE_FAILED')
        record=json.loads((Path(self.temp.name)/'requests.jsonl').read_text())
        self.assertEqual(record['imageSha256'],digest)
        with Image.open(io.BytesIO(blob)) as image:
            self.assertEqual(record['imageSize'],list(ImageOps.exif_transpose(image).size))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
    def test_downloader_restricts_origin_scheme_redirect_size(self):
        downloader=Downloader(['http://127.0.0.1:8888'])
        for url in ['file:///etc/passwd','http://other/image','http://user:password@127.0.0.1:8888/a']:
            with self.assertRaises(contract.Failure):downloader(url)
        from ai_api.server import NoRedirect,MAX_BYTES
        with self.assertRaises(contract.Failure):NoRedirect().redirect_request(None,None,None,None,None,None)
        response=SimpleNamespace(status=200,headers={'Content-Length':str(MAX_BYTES+1)})
        class Context:
            def __enter__(self):return response
            def __exit__(self,*args):pass
        with patch.object(downloader.opener,'open',return_value=Context()):
            with self.assertRaises(contract.Failure) as error:downloader('http://127.0.0.1:8888/image')
        self.assertEqual(error.exception.code,'IMAGE_TOO_LARGE')


if __name__=='__main__':unittest.main(verbosity=2)
