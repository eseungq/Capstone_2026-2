"""Development e02 server; does not start training or activate backend models."""
import argparse,json,logging,os,signal
from functools import partial
from pathlib import Path
from ai_api import backend_contract
from ai_api.e02_engine import CandidateEngine,MANIFEST
from ai_api.e02_service import CandidateService
from ai_api.server import Server,Downloader
from ai_api.e02_integration import wire
from ai_api.e02_integration.handler import Handler
from ai_api.e02_integration.timing import REQUEST_TIMINGS, STAGES, measure
class IntegrationService(CandidateService):
    def __init__(self,engine,version,downloader,*args,**kwargs):
        kwargs['response_profile']=backend_contract.PROFILE
        super().__init__(engine,version,partial(measure,'imageDownloadMs',downloader),*args,**kwargs)
        self.response_profile=wire.PROFILE

    def predict(self,body,*,request_id=None):
        token=REQUEST_TIMINGS.set(dict.fromkeys(STAGES))
        try:
            return super().predict(body,request_id=request_id)
        finally:
            REQUEST_TIMINGS.reset(token)

    def audit(self,record):
        timings=REQUEST_TIMINGS.get()
        if timings is not None:
            record={**record,**timings}
        super().audit(record)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=MANIFEST)
    p.add_argument('--image-origin',action='append',required=True)
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8771)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--ready-file',type=Path)
    p.add_argument('--gpu-lock',type=Path)
    a=p.parse_args();logging.basicConfig(level=logging.INFO)
    gpu_lock=None
    if a.gpu_lock:
        import fcntl
        a.gpu_lock.parent.mkdir(parents=True,exist_ok=True)
        gpu_lock=a.gpu_lock.open('a')
        fcntl.flock(gpu_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    engine=CandidateEngine(a.manifest);version=engine.metadata['model_version']
    service=IntegrationService(engine,version,Downloader(a.image_origin),a.runtime,cam_format='jpeg',jpeg_quality=90)
    server=Server((a.host,a.port),Handler);server.service=service
    def ready(value):
        if a.ready_file:
            a.ready_file.parent.mkdir(parents=True,exist_ok=True)
            record=dict(ready=value,pid=os.getpid(),modelVersion=version,modelSha256=engine.metadata['model_sha256'],host=a.host,port=server.server_port,contractProfile=wire.PROFILE,calibratorVersion=None,backendModelRegistered=False)
            temp=a.ready_file.with_suffix('.tmp');temp.write_text(json.dumps(record)+'\n');temp.replace(a.ready_file)
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    ready(True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();ready(False)
if __name__=='__main__':main()
