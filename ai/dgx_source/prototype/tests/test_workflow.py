"""Non-GPU HTTP/storage checks. Stored fixture is NEVER presented as new inference."""
import io
import json
import sys
import tempfile
import threading
import unittest
import unittest.mock
from types import SimpleNamespace
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Service,Store,Handler,MAX_BYTES


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=Service(self.temp.name,None)
        self.thread=None
        try:
            self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        except PermissionError:
            print('[검사 범위] TCP socket blocked; HTTP parser/handler tested with in-memory streams, not live network.',flush=True)
            self.server=SimpleNamespace(server_port=8765,service=self.service)
        else:
            self.server.service=self.service
            self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        if self.thread:
            self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()
    def request(self,path,data=None,raw=False,token=True,headers=None):
        h={'X-Door-Token':self.service.token} if token else {}
        if data is not None and not raw:
            data=json.dumps(data).encode();h['Content-Type']='application/json'
        if headers:h.update(headers)
        if self.thread is None:
            method='POST' if data is not None else 'GET'
            h.update(Host=f'127.0.0.1:{self.server.server_port}',Connection='close')
            if data is not None:h.setdefault('Content-Length',str(len(data)))
            wire=(f'{method} {path} HTTP/1.0\r\n'+''.join(f'{k}: {v}\r\n' for k,v in h.items())+'\r\n').encode()+(data or b'')
            class Connection:
                def __init__(self):self.output=bytearray()
                def makefile(self,*args):return io.BytesIO(wire)
                def sendall(self,blob):self.output.extend(blob)
                def settimeout(self,value):pass
            connection=Connection()
            Handler(connection,('127.0.0.1',0),self.server)
            head,body=bytes(connection.output).split(b'\r\n\r\n',1)
            code=int(head.split(b' ')[1])
            return code,json.loads(body) if b'application/json' in head else body
        try:
            with urlopen(Request(self.base+path,data=data,headers=h),timeout=10) as r:
                body=r.read();return r.status,json.loads(body) if r.headers['Content-Type'].startswith('application/json') else body
        except HTTPError as e:return e.code,json.load(e)
    def image(self):
        # EXIF orientation 6 rotates 20x10 to 10x20.
        image=Image.new('RGB',(20,10),'red');exif=Image.Exif();exif[274]=6
        b=io.BytesIO();image.save(b,format='JPEG',exif=exif);return b.getvalue()
    def upload(self):
        status,item=self.request('/api/uploads',self.image(),True,headers={'X-File-Name':'%EC%96%91%ED%92%88.jpg'})
        self.assertEqual(status,201);return item
    def test_upload_error_handling_and_no_inference_fallback(self):
        item=self.upload();ident=item['id'];self.assertEqual((item['width'],item['height']),(10,20))
        self.assertIsNone(item['prediction'])
        self.assertEqual(item['review_state'],'not_reviewed')
        self.assertEqual(self.request(f'/api/records/{ident}/inspect',{})[0],503)
        self.assertIsNone(self.service.store.get(ident)['prediction'])
        self.assertEqual(self.request(f'/api/records/{ident}/review',{'judgment':'양품'})[0],409)
        self.assertEqual(self.request('/api/uploads',b'not an image',True)[0],400)
        image=Image.new('RGB',(2,2));b=io.BytesIO();image.save(b,format='GIF')
        self.assertEqual(self.request('/api/uploads',b.getvalue(),True)[0],400)
        self.assertEqual(self.request('/api/uploads',self.image(),True,False)[0],403)
        self.assertEqual(self.request('/api/uploads',self.image(),True,headers={'Content-Length':str(MAX_BYTES+1)})[0],413)
        with unittest.mock.patch('app.MAX_PIXELS',10):
            self.assertEqual(self.request('/api/uploads',self.image(),True)[0],413)
    def test_real_internal_validation_upload_only(self):
        import csv,hashlib
        root=Path('/path/to/private/validated-project')
        with (root/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig',newline='') as f:
            sample=next(csv.DictReader(f))
        source=Path(sample['image_path']);blob=source.read_bytes();digest=hashlib.sha256(blob).hexdigest()
        code,item=self.request('/api/uploads',blob,True,headers={'X-File-Name':'unrelated_name.webp'})
        self.assertEqual(code,201);self.assertEqual(item['upload_sha256'],digest)
        self.assertEqual((self.service.store.directory(item['id'])/'upload.bin').read_bytes(),blob)
        self.assertEqual(self.request(f'/api/records/{item["id"]}/inspect',{})[0],503)
        self.assertIsNone(self.service.store.get(item['id'])['prediction'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
    def test_immutable_prediction_review_history_and_persistence(self):
        item=self.upload();ident=item['id']
        fixture={'predicted_class':1,'raw_defect_score':0.8,'processing_ms':1.2,'model':{'model_sha256':'TEST_FIXTURE_NOT_GPU'}}
        self.service.store.save_prediction(ident,fixture)
        self.service.store.save_prediction(ident,dict(fixture,predicted_class=0))
        self.assertEqual(self.service.store.get(ident)['prediction'],fixture)
        for judgment in ('양품','판단 보류'):
            status,row=self.request(f'/api/records/{ident}/review',{'judgment':judgment,'note':'<script>text only</script>'})
            self.assertEqual(status,200);self.assertEqual(row['prediction'],fixture)
        row=self.request(f'/api/records/{ident}')[1]
        self.assertEqual(len(row['reviews']),2);self.assertEqual(row['review']['judgment'],'판단 보류')
        self.assertEqual(row['review_state'],'deferred')
        self.assertEqual(Store(self.temp.name).get(ident),row)
        self.assertEqual(self.request(f'/api/records/{ident}/cam',{'target_class':1})[0],503)
        self.assertEqual(self.request(f'/api/records/{ident}')[1]['prediction'],fixture)
        self.assertEqual(self.request('/api/records')[1]['total'],1)
        self.assertEqual(self.request(f'/assets/{ident}/preview.jpg')[0],200)
        self.assertEqual(self.request(f'/assets/{ident}/original.png')[0],200)
        self.assertEqual(self.request(f'/assets/{ident}/upload.bin')[0],404)
        self.assertEqual(self.request('/assets/../../history.sqlite3')[0],404)
        status,page=self.request('/');self.assertEqual(status,200)
        self.assertIn(self.service.token.encode(),page);self.assertNotIn(b'__TOKEN__',page)


if __name__=='__main__':
    import unittest.mock
    unittest.main()
