"""Confirmed backend-v4 CAM payload; no classification or policy changes."""
from copy import deepcopy
import math
from ai_api.backend_contract import error, inventory
PROFILE='backend-v4-1028-e02-integration'
PENDING_PROFILE='unused-legacy-pending'
def success(response, elapsed_ms):
    if not math.isfinite(elapsed_ms) or elapsed_ms < 0:
        raise ValueError('Invalid duration')
    result=deepcopy(response)
    cam=result['gradcam'];state=cam['status'];quality=result['predictedQuality']
    if quality=='GOOD':
        if state!='NOT_GENERATED_GOOD':raise ValueError('Unexpected GOOD CAM state')
        result['gradcam']=None
    elif quality=='DEFECT':
        if state in ('ZERO_MAP','CONSTANT_MAP'):
            result['gradcam']=dict(targetClass='DEFECT',status='NO_ACTIVATION',mapType=state,format=None,imageBase64=None)
        elif state=='FAILED':result['gradcam']=None
        elif state=='GENERATED':
            mime=cam['mimeType']
            if mime not in ('image/png','image/jpeg') or not cam.get('base64'):raise ValueError('Invalid generated CAM')
            result['gradcam']=dict(targetClass='DEFECT',status='GENERATED',format='jpeg' if mime=='image/jpeg' else 'png',imageBase64=cam['base64'])
        else:raise ValueError('Unexpected DEFECT CAM state')
    else:raise ValueError('Unknown predicted quality')
    result['inferenceTimeMs']=int(elapsed_ms)
    return result,PROFILE,{}
