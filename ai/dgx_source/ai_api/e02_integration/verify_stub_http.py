"""Real loopback HTTP checks with a stub model; never loads GPU or data."""
import json,tempfile,threading,uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from ai_api import contract
from ai_api.server import Server,validate_request
from ai_api.e02_integration.handler import Handler
from ai_api.e02_integration import wire
VERSION='door-swin-tiny-e02-28a2dd1cb40b-dev'
class StubService:
    response_profile=wire.PROFILE
    def __init__(self):self.audits=[]
    def audit(self,row):self.audits.append(row)
    def model_inventory(self):return {'models':[dict(modelVersion=VERSION,partCode='DOOR',available=True,modelSha256='fixture')]}
    def predict(self,body,request_id=None):
        validate_request(body,VERSION)
        state=body['imageUrl'].rsplit('/',1)[-1]
        if state=='classification_failure':raise contract.Failure('INFERENCE_FAILED',503)
        if state=='GOOD':quality='GOOD';cam=contract.gradcam('NOT_GENERATED_GOOD')
        elif state in ('ZERO_MAP','CONSTANT_MAP','FAILED'):quality='DEFECT';cam=contract.gradcam(state)
        else:quality='DEFECT';cam=contract.gradcam('GENERATED','fixture-base64',mime_type='image/jpeg')
        return dict(inspectionId=body['inspectionId'],modelVersion=VERSION,predictedQuality=quality,rawDefectProbability=.1 if quality=='GOOD' else .9,calibratedDefectProbability=None,calibratorVersion=None,imageWidth=640,imageHeight=480,gradcam=cam,inferenceTimeMs=.1)
def main():
    server=Server(('127.0.0.1',0),Handler);server.service=StubService();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    opener=build_opener(ProxyHandler({}));origin=f'http://127.0.0.1:{server.server_port}';checks=[]
    def call(path,body=None,raw=None):
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        try:
            with opener.open(Request(origin+path,data=data,headers={'Content-Type':'application/json'}),timeout=10) as res:return res.status,json.load(res),dict(res.headers)
        except HTTPError as e:return e.code,json.load(e),dict(e.headers)
    try:
        code,result,_=call('/internal/v1/models');assert code==200 and result=={'data':[dict(modelVersion=VERSION,partCode='DOOR',calibratorVersion=None,loadable=True)]};checks.append('inventory')
        for state in ['GOOD','GENERATED','ZERO_MAP','CONSTANT_MAP','FAILED','classification_failure','wrong_model','unsupported_part']:
            iid=str(uuid.uuid4());body=dict(inspectionId=iid,partCode='OTHER' if state=='unsupported_part' else 'DOOR',requestedModelVersion='old-version' if state=='wrong_model' else VERSION,imageUrl='http://fixture/'+state)
            code,result,headers=call('/internal/v1/predict',body)
            expected={'classification_failure':503,'wrong_model':409,'unsupported_part':422}.get(state,200)
            assert code==expected,(state,code,result)
            if code!=200:
                assert set(result['error'])=={'code','message','traceId','inspectionId'} and result['error']['inspectionId']==iid and result['error']['traceId']==headers['X-Trace-Id']
            else:
                assert result['inspectionId']==iid and result['modelVersion']==VERSION
                assert result['calibratedDefectProbability'] is None and result['calibratorVersion'] is None
                assert headers['X-AI-Contract-Profile']==wire.PROFILE and 'X-AI-Contract-Pending' not in headers
                assert type(result['inferenceTimeMs'])==int and result['inferenceTimeMs']>=0
                cam=result['gradcam']
                if state in ['GOOD','FAILED']:assert cam is None
                elif state in ['ZERO_MAP','CONSTANT_MAP']:assert cam==dict(targetClass='DEFECT',status='NO_ACTIVATION',mapType=state,format=None,imageBase64=None)
                else:assert cam['status']=='GENERATED' and cam['format']=='jpeg' and cam['targetClass']=='DEFECT'
            checks.append(state)
        code,result,_=call('/internal/v1/predict',raw=b'{broken');assert code==400 and result['error']['inspectionId'] is None;checks.append('invalid_json')
        code,result,_=call('/wrong-path');assert code==404;checks.append('not_found')
        return dict(status='passed',scope='real loopback HTTP with stub model; no GPU, weights or images',checks=checks)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=='__main__':print(json.dumps(main(),ensure_ascii=False))
