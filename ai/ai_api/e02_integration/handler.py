"""Isolated e02 wire handler; preserves the hash-locked legacy handler."""
import json,time,uuid
from datetime import datetime,timezone
from ai_api.server import Handler as LegacyHandler, MAX_JSON
from ai_api import contract
from ai_api.e02_integration import wire as wire_contract

class Handler(LegacyHandler):
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
        backend=self.server.service.response_profile==wire_contract.PROFILE
        def send_error(status,code):
            payload=wire_contract.error(ident,code,trace_id) if backend else contract.error(ident,code)
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
                wire,profile,headers=wire_contract.success(result,elapsed)
                headers['X-Trace-Id']=trace_id
                self.send(200,wire,profile=profile,headers=headers,
                          timing_started=started if profile==wire_contract.PROFILE else None)
                self.server.service.audit(dict(event='wire_response',requestId=trace_id,inspectionId=ident,
                    at=datetime.now(timezone.utc).isoformat(),contractProfile=profile,status=200,
                    classificationTimeMs=result['inferenceTimeMs'],preAdapterElapsedMs=elapsed,
                    wireInferenceTimeMs=wire['inferenceTimeMs'],camComputationState=result['gradcam']['status'],
                    wireTimeDefinition='handler_entry_before_body_read_to_before_json_serialization',
                    backendCompatibleKnownCase=profile==wire_contract.PROFILE))
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
        backend=self.server.service.response_profile==wire_contract.PROFILE
        trace_id=uuid.uuid4().hex
        def error(status,code):
            self.send(status,wire_contract.error(None,code,trace_id) if backend else contract.error(None,code),headers={'X-Trace-Id':trace_id})
        if self.path=='/internal/v1/models':
            try:
                inventory=self.server.service.model_inventory()
                headers={'X-Trace-Id':trace_id}
                if backend:
                    row=inventory['models'][0]
                    if row.get('modelSha256'):headers['X-AI-Model-SHA256']=row['modelSha256']
                    inventory=wire_contract.inventory(inventory)
                self.send(200,inventory,headers=headers)
            except Exception:error(500,'INTERNAL_ERROR')
        else:error(404,'NOT_FOUND')
