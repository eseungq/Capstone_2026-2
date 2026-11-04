"""Stdlib HTTP API sharing the unchanged validated GPU engine."""
import argparse
import base64
import hashlib
import io
import json
import logging
import os
import signal
import math
import tempfile
import threading
import time
import uuid
import warnings
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from PIL import Image, ImageOps
from ai_api import contract, backend_contract
from ai_api.cam_encoding import encode_overlay

MAX_BYTES=40*1024*1024
MAX_PIXELS=120_000_000
MAX_JSON=16*1024
Image.MAX_IMAGE_PIXELS=MAX_PIXELS
LOG=logging.getLogger('door_api')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise contract.Failure('IMAGE_ACCESS_FAILED', 422)


class Downloader:
    def __init__(self, origins, timeout=20):
        self.origins=set(origins)
        self.timeout=timeout
        self.opener=build_opener(ProxyHandler({}), NoRedirect())
        for origin in self.origins:
            parts=urlsplit(origin)
            if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
                raise ValueError('Allowed origins must be exact http(s)://host[:port], without trailing slash')

    def __call__(self, url):
        try:
            parts=urlsplit(url)
            if parts.scheme not in ('http','https') or parts.username or parts.password or parts.fragment or not parts.hostname:
                raise contract.Failure('INVALID_IMAGE_URL',400)
            if f'{parts.scheme}://{parts.netloc}' not in self.origins:
                raise contract.Failure('IMAGE_ORIGIN_NOT_ALLOWED',422)
            with self.opener.open(Request(url,headers={'Accept':'image/*'}),timeout=self.timeout) as response:
                if response.status!=200: raise contract.Failure('IMAGE_ACCESS_FAILED',422)
                length=response.headers.get('Content-Length')
                if length is not None and int(length)>MAX_BYTES: raise contract.Failure('IMAGE_TOO_LARGE',413)
                # read1 avoids waiting for a whole large body before checking the deadline.
                deadline=time.monotonic()+self.timeout
                chunks=[];total=0
                while True:
                    if time.monotonic()>deadline: raise contract.Failure('IMAGE_ACCESS_FAILED',422)
                    chunk=response.read1(min(64*1024,MAX_BYTES+1-total))
                    if time.monotonic()>deadline: raise contract.Failure('IMAGE_ACCESS_FAILED',422)
                    if not chunk: break
                    total+=len(chunk)
                    if total>MAX_BYTES: raise contract.Failure('IMAGE_TOO_LARGE',413)
                    chunks.append(chunk)
                return b''.join(chunks)
        except contract.Failure: raise
        except Exception as exc:
            raise contract.Failure('IMAGE_ACCESS_FAILED',422) from exc


def display_size(blob):
    if not blob or len(blob)>MAX_BYTES: raise contract.Failure('IMAGE_TOO_LARGE',413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(blob)) as image:
                if image.format not in ('JPEG','PNG','WEBP') or getattr(image,'n_frames',1)!=1:
                    raise contract.Failure('INVALID_IMAGE',422)
                if image.width*image.height>MAX_PIXELS: raise contract.Failure('IMAGE_TOO_LARGE',413)
                image.verify()
            with Image.open(io.BytesIO(blob)) as image:
                original=ImageOps.exif_transpose(image).convert('RGB')
                original.load()
                return original.size
    except contract.Failure: raise
    except Exception as exc: raise contract.Failure('INVALID_IMAGE',422) from exc


def validate_request(body, version):
    fields={'inspectionId','partCode','requestedModelVersion','imageUrl'}
    if not isinstance(body,dict) or set(body)!=fields or any(not isinstance(v,str) or not v or len(v)>4096 for v in body.values()):
        raise contract.Failure('INVALID_REQUEST',400)
    if len(body['inspectionId'])>128 or any(ord(c)<32 for c in body['inspectionId']):
        raise contract.Failure('INVALID_REQUEST',400)
    if body['partCode']!='DOOR': raise contract.Failure('UNSUPPORTED_PART',422)
    if body['requestedModelVersion']!=version: raise contract.Failure('MODEL_VERSION_MISMATCH',409)


class Service:
    def __init__(self, engine, version, downloader, runtime, response_profile=contract.PROFILE,cam_format='png',jpeg_quality=90):
        if not version or version.startswith('mock-'): raise ValueError('A real, explicit model version is required')
        if response_profile not in (contract.PROFILE,backend_contract.PROFILE):raise ValueError('Unknown response profile')
        self.response_profile=response_profile
        if cam_format not in ('png','jpeg') or not isinstance(jpeg_quality,int) or isinstance(jpeg_quality,bool) or not 1<=jpeg_quality<=95:raise ValueError('Invalid CAM encoding settings')
        if cam_format=='jpeg' and response_profile!=backend_contract.PROFILE:raise ValueError('JPEG requires the explicit backend response profile')
        self.cam_format,self.jpeg_quality=cam_format,jpeg_quality
        self.engine,self.version,self.downloader=engine,version,downloader
        self.runtime=Path(runtime);self.runtime.mkdir(parents=True,exist_ok=True)
        self.model_lock=threading.Lock()
        self.audit_lock=threading.Lock()
        self.slots=threading.BoundedSemaphore(4)

    def predict(self, body, *, request_id=None):
        ident=body.get('inspectionId') if isinstance(body,dict) and isinstance(body.get('inspectionId'),str) else None
        if ident is not None and (len(ident)>128 or any(ord(c)<32 for c in ident)): ident=None
        request_id=request_id or uuid.uuid4().hex
        record=dict(requestId=request_id,inspectionId=ident,at=datetime.now(timezone.utc).isoformat(),
                    contractProfile=self.response_profile,internalComputationProfile=contract.PROFILE)
        if not self.slots.acquire(blocking=False):
            self.audit(dict(record,status=503,error='BUSY'))
            raise contract.Failure('BUSY',503)
        try:
            validate_request(body,self.version)
            if self.engine is None: raise contract.Failure('MODEL_UNAVAILABLE',503)
            blob=self.downloader(body['imageUrl'])
            size=display_size(blob)
            record.update(imageSha256=hashlib.sha256(blob).hexdigest(),imageSize=list(size),modelVersion=self.version)
            with tempfile.TemporaryDirectory(prefix=request_id+'_',dir=self.runtime) as folder:
                dest=Path(folder);image=dest/'upload.bin';image.write_bytes(blob)
                # Same lock covers ALL predict and CAM operations on the shared model.
                with self.model_lock:
                    try:
                        prediction=self.engine.predict(image)
                        score=prediction['raw_defect_score'];ms=prediction['processing_ms']
                        if not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1 or not isinstance(ms,(int,float)) or not math.isfinite(ms) or ms<0 or prediction['predicted_class']!=int(score>=0.5):
                            raise ValueError('Invalid engine prediction')
                    except Exception as exc: raise contract.Failure('INFERENCE_FAILED',503) from exc
                    cam=contract.gradcam('NOT_GENERATED_GOOD')
                    if prediction['predicted_class']==1:
                        try:
                            info=self.engine.explain(image,dest,1)
                            if not info.get('state_unchanged') or not info.get('eval_mode'): raise ValueError('Invalid CAM model state')
                            raw_zero=info['raw_min']==0 and info['raw_max']==0
                            if info['constant']:
                                cam=contract.gradcam('ZERO_MAP' if raw_zero else 'CONSTANT_MAP')
                            else:
                                overlay=dest/'cam1.png'
                                png=overlay.read_bytes()
                                encoding_started=time.perf_counter()
                                encoded,mime=encode_overlay(png,size,self.cam_format,self.jpeg_quality)
                                record.update(camFormat=self.cam_format,camJpegQuality=self.jpeg_quality if self.cam_format=='jpeg' else None,
                                    camEncodedBytes=len(encoded),camEncodingMs=(time.perf_counter()-encoding_started)*1000,
                                    camSourceOverlaySha256=hashlib.sha256(png).hexdigest())
                                cam=contract.gradcam('GENERATED',base64.b64encode(encoded).decode('ascii'),mime_type=mime)
                        except Exception:
                            LOG.warning('Grad-CAM failed inspectionId=%r requestId=%s',ident,request_id)
                            cam=contract.gradcam('FAILED')
            result=contract.success(ident,self.version,prediction,size,cam)
            record.update(status=200,predictedQuality=result['predictedQuality'],rawDefectProbability=score,gradcamStatus=cam['status'],inferenceTimeMs=ms)
            return result
        except contract.Failure as exc:
            record.update(status=exc.status,error=exc.code)
            raise
        except Exception as exc:
            record.update(status=500,error='INTERNAL_ERROR')
            raise contract.Failure('INTERNAL_ERROR',500) from exc
        finally:
            self.slots.release()
            self.audit(record)

    def model_inventory(self):
        """Development JSON proposal; availability is tied to the loaded DOOR engine.

        Not a model registry/activation API. Recheck checkpoint bytes against the
        strict-loaded engine metadata; an entry in configuration alone is insufficient.
        """
        metadata=getattr(self.engine,'metadata',{}) if self.engine is not None else {}
        available=False
        try:
            from prototype.engine import RUN,sha
            available=(self.engine is not None and not self.engine.model.training
                       and metadata.get('model_sha256')==sha(RUN/'best.pt'))
        except (OSError,AttributeError):pass
        return {'models':[{'partCode':'DOOR','modelVersion':self.version,
                           'available':bool(available),'modelName':metadata.get('model_name'),
                           'modelSha256':metadata.get('model_sha256') if available else None}],
                'schemaStatus':'development-proposal-field-layout-pending'}

    def audit(self, record):
        # Never logs imageUrl (which may contain signed credentials), image bytes, or raw exceptions.
        try:
            with self.audit_lock, (self.runtime/'requests.jsonl').open('a') as stream:
                stream.write(json.dumps(record,ensure_ascii=False,allow_nan=False)+'\n')
        except OSError:
            LOG.error('Audit write failed inspectionId=%r requestId=%s',record['inspectionId'],record['requestId'])


class Handler(BaseHTTPRequestHandler):
    server_version='DoorAI/development'
    def log_message(self,*args): pass
    def send(self,status,body,*,profile=None,headers=None,timing_started=None):
        if timing_started is not None:body['inferenceTimeMs']=int((time.perf_counter()-timing_started)*1000)
        blob=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(blob)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-AI-Contract-Profile',profile or self.server.service.response_profile)
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(blob)
    def do_POST(self):
        started=time.perf_counter()
        trace_id=uuid.uuid4().hex
        ident=None
        serviced=False
        backend=self.server.service.response_profile==backend_contract.PROFILE
        def send_error(status,code):
            payload=backend_contract.error(ident,code,trace_id) if backend else contract.error(ident,code)
            self.send(status,payload,headers={'X-Trace-Id':trace_id})
        try:
            self.connection.settimeout(30)
            if self.path!='/internal/v1/predict': raise contract.Failure('NOT_FOUND',404)
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json': raise contract.Failure('INVALID_REQUEST',400)
            if self.headers.get('Transfer-Encoding'): raise contract.Failure('INVALID_REQUEST',400)
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or not lengths[0].isdigit(): raise contract.Failure('INVALID_REQUEST',400)
            size=int(lengths[0])
            if not 0<size<=MAX_JSON: raise contract.Failure('INVALID_REQUEST',400)
            blob=self.rfile.read(size)
            if len(blob)!=size: raise contract.Failure('INVALID_REQUEST',400)
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result: raise ValueError('Duplicate key')
                    result[key]=value
                return result
            try: body=json.loads(blob,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError,UnicodeError): raise contract.Failure('INVALID_REQUEST',400)
            candidate=body.get('inspectionId') if isinstance(body,dict) else None
            if isinstance(candidate,str) and len(candidate)<=128 and not any(ord(c)<32 for c in candidate): ident=candidate
            serviced=True
            result=self.server.service.predict(body,request_id=trace_id)
            if backend:
                elapsed=(time.perf_counter()-started)*1000
                wire,profile,headers=backend_contract.success(result,elapsed)
                headers['X-Trace-Id']=trace_id
                self.send(200,wire,profile=profile,headers=headers,
                          timing_started=started if profile==backend_contract.PROFILE else None)
                self.server.service.audit(dict(event='wire_response',requestId=trace_id,inspectionId=ident,
                    at=datetime.now(timezone.utc).isoformat(),contractProfile=profile,status=200,
                    classificationTimeMs=result['inferenceTimeMs'],preAdapterElapsedMs=elapsed,
                    wireInferenceTimeMs=wire['inferenceTimeMs'],camComputationState=result['gradcam']['status'],
                    wireTimeDefinition='handler_entry_before_body_read_to_before_json_serialization',
                    backendCompatibleKnownCase=profile==backend_contract.PROFILE))
            else:self.send(200,result)
        except contract.Failure as exc:
            if not serviced:
                self.server.service.audit(dict(requestId=trace_id,inspectionId=ident,
                    at=datetime.now(timezone.utc).isoformat(),contractProfile=self.server.service.response_profile,status=exc.status,error=exc.code))
            send_error(exc.status,exc.code)
        except Exception:
            if not serviced:
                self.server.service.audit(dict(requestId=trace_id,inspectionId=ident,
                    at=datetime.now(timezone.utc).isoformat(),contractProfile=self.server.service.response_profile,status=500,error='INTERNAL_ERROR'))
            send_error(500,'INTERNAL_ERROR')
    def do_GET(self):
        backend=self.server.service.response_profile==backend_contract.PROFILE
        trace_id=uuid.uuid4().hex
        def error(status,code):
            self.send(status,backend_contract.error(None,code,trace_id) if backend else contract.error(None,code),headers={'X-Trace-Id':trace_id})
        if self.path=='/internal/v1/models':
            try:
                inventory=self.server.service.model_inventory()
                headers={'X-Trace-Id':trace_id}
                if backend:
                    row=inventory['models'][0]
                    if row.get('modelSha256'):headers['X-AI-Model-SHA256']=row['modelSha256']
                    inventory=backend_contract.inventory(inventory)
                self.send(200,inventory,headers=headers)
            except Exception:error(500,'INTERNAL_ERROR')
        else:error(404,'NOT_FOUND')


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.threads=threading.BoundedSemaphore(8)
        super().__init__(*args,**kwargs)
    def process_request(self,request,client_address):
        if not self.threads.acquire(blocking=False):
            self.shutdown_request(request);return
        try: super().process_request(request,client_address)
        except Exception:
            self.threads.release();raise
    def process_request_thread(self,*args):
        try: super().process_request_thread(*args)
        finally: self.threads.release()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--development-contract',action='store_true',required=True,
                        help='Explicitly acknowledge that JSON/status/error choices are NOT a confirmed v4 contract')
    parser.add_argument('--model-version',required=True)
    parser.add_argument('--response-profile',choices=[contract.PROFILE,backend_contract.PROFILE],default=contract.PROFILE,
                        help='Opt-in partial backend payload adapter; zero/constant CAM keeps explicit legacy development response')
    parser.add_argument('--cam-format',choices=['png','jpeg'],default='png',help='Display CAM encoding; JPEG requires backend profile; PNG is preserved default')
    parser.add_argument('--jpeg-quality',type=int,default=90,help='JPEG quality 1..95, explicit 4:2:0 sampling; does not affect model or CAM computation')
    parser.add_argument('--image-origin',action='append',required=True)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--runtime',type=Path,default=Path(__file__).parent/'runtime')
    parser.add_argument('--ready-file',type=Path,help='Optional local readiness record for supervised development restart verification')
    args=parser.parse_args()
    if not 1<=args.jpeg_quality<=95:parser.error('--jpeg-quality must be 1..95')
    if args.cam_format=='jpeg' and args.response_profile!=backend_contract.PROFILE:parser.error('JPEG requires --response-profile '+backend_contract.PROFILE)
    logging.basicConfig(level=logging.INFO)
    from prototype.engine import Engine
    engine=Engine()  # Fails startup without the validated model/environment. No fallback model.
    service=Service(engine,args.model_version,Downloader(args.image_origin),args.runtime,response_profile=args.response_profile,
                    cam_format=args.cam_format,jpeg_quality=args.jpeg_quality)
    server=Server((args.host,args.port),Handler);server.service=service
    def readiness(ready):
        if args.ready_file:
            args.ready_file.parent.mkdir(parents=True,exist_ok=True)
            record={'ready':ready,'pid':os.getpid(),'host':args.host,'port':server.server_port,
                    'modelVersion':args.model_version,'modelSha256':engine.metadata['model_sha256'],
                    'contractProfile':args.response_profile,'camFormat':args.cam_format,
                    'jpegQuality':args.jpeg_quality if args.cam_format=='jpeg' else None}
            temp=args.ready_file.with_suffix('.tmp');temp.write_text(json.dumps(record)+'\n');temp.replace(args.ready_file)
    def stop_signal(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop_signal)
    readiness(True)
    LOG.info('Ready profile=%s modelVersion=%s sha256=%s bind=%s:%s',args.response_profile,args.model_version,engine.metadata['model_sha256'],args.host,server.server_port)
    try: server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();readiness(False)


if __name__=='__main__': main()
