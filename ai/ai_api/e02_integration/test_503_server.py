"""TEST ONLY: proxy real model inventory, return fixed 503 for predictions. No GPU."""
import argparse,json,logging,signal,time,uuid,os
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from ai_api.e02_integration.wire import error
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,payload):
        blob=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(blob)));self.send_header('Cache-Control','no-store');self.send_header('X-AI-Test-Only','forced-503-no-model-inference');self.end_headers();self.wfile.write(blob)
    def do_GET(self):
        if self.path!='/internal/v1/models':self.send(404,error(None,'NOT_FOUND',uuid.uuid4().hex));return
        try:
            with build_opener(ProxyHandler({})).open(self.server.inventory_url,timeout=3) as response:inventory=json.load(response)
            self.send(200,inventory)
        except Exception:self.send(503,error(None,'MODEL_UNAVAILABLE',uuid.uuid4().hex))
    def do_POST(self):
        self.connection.settimeout(10);iid=None;trace=uuid.uuid4().hex
        if self.path!='/internal/v1/predict':self.send(404,error(None,'NOT_FOUND',trace));return
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=16384:raise ValueError()
            data=json.loads(self.rfile.read(n));candidate=data.get('inspectionId')
            if isinstance(candidate,str) and len(candidate)<=128 and not any(ord(c)<32 for c in candidate):iid=candidate
        except Exception:self.send(400,error(None,'INVALID_REQUEST',trace));return
        payload=error(iid,'INFERENCE_FAILED',trace)
        self.send(503,payload)
        with self.server.audit_path.open('a') as f:f.write(json.dumps(dict(at=datetime.now(timezone.utc).isoformat(),inspectionId=iid,traceId=trace,status=503,error='INFERENCE_FAILED',forced=True))+'\n')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8772);p.add_argument('--runtime',type=Path,required=True);a=p.parse_args();a.runtime.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer((a.host,a.port),Handler);server.daemon_threads=True;server.inventory_url=os.environ.get('AI_PRIMARY_API_ORIGIN','http://127.0.0.1:8771').rstrip('/')+'/internal/v1/models';server.audit_path=a.runtime/'requests.jsonl'
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print('[TEST ONLY 503 READY]',a.host,a.port,flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
