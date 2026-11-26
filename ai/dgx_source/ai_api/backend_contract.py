"""Confirmed 10/28 payload fields, with an explicit legacy fallback for unresolved CAMs.

Opt-in development profile. A zero/constant response is NOT backend-compatible;
it preserves classification and the old computation state, never declares failure.
The backend owner must decide persistence/display semantics before mixed integration.
"""
from copy import deepcopy
import math

PROFILE='backend-v4-1028-partial'
PENDING_PROFILE='development-zero-map-contract-pending'
MESSAGES={
    'INVALID_REQUEST':'Invalid prediction request.',
    'NOT_FOUND':'Endpoint not found.',
    'UNSUPPORTED_PART':'Requested part is not supported.',
    'MODEL_VERSION_MISMATCH':'Requested model version is not loaded.',
    'MODEL_UNAVAILABLE':'Requested model is unavailable.',
    'INVALID_IMAGE_URL':'Invalid image URL.',
    'IMAGE_ORIGIN_NOT_ALLOWED':'Image origin is not allowed.',
    'IMAGE_ACCESS_FAILED':'Image could not be retrieved.',
    'IMAGE_TOO_LARGE':'Image exceeds the supported limits.',
    'INVALID_IMAGE':'Image could not be decoded.',
    'INFERENCE_FAILED':'Classification could not be completed.',
    'BUSY':'Prediction capacity is temporarily exhausted.',
    'INTERNAL_ERROR':'Prediction service could not complete the request.',
}


def success(response,elapsed_ms):
    if not math.isfinite(elapsed_ms) or elapsed_ms<0:raise ValueError('Invalid duration')
    result=deepcopy(response);state=result['gradcam']['status']
    if state in ('ZERO_MAP','CONSTANT_MAP'):
        # Keep the original development response exactly; null would be FAILED
        # under the current backend and would misrepresent a successful computation.
        return result,PENDING_PROFILE,{'X-AI-Contract-Pending':'zero-constant-map-semantics'}
    if state=='NOT_GENERATED_GOOD':
        if result['predictedQuality']!='GOOD':raise ValueError('Invalid GOOD CAM state')
        result['gradcam']=None
    elif state=='FAILED':result['gradcam']=None
    elif state=='GENERATED':
        if result['predictedQuality']!='DEFECT':raise ValueError('Invalid DEFECT CAM state')
        mime=result['gradcam']['mimeType']
        if mime not in ('image/png','image/jpeg'):raise ValueError('Unknown CAM MIME type')
        result['gradcam']={'targetClass':'DEFECT','format':'jpeg' if mime=='image/jpeg' else 'png','imageBase64':result['gradcam']['base64']}
    else:raise ValueError('Unknown CAM computation state')
    # Integer elapsed milliseconds, truncated as in the supplied Mock example.
    # Never use classification_ms as a substitute for this measured interval.
    result['inferenceTimeMs']=int(elapsed_ms)
    return result,PROFILE,{}


def error(inspection_id,code,trace_id):
    return {'error':{'code':code,'message':MESSAGES.get(code,MESSAGES['INTERNAL_ERROR']),
                     'traceId':trace_id,'inspectionId':inspection_id}}


def inventory(internal):
    return {'data':[{'modelVersion':row['modelVersion'],'partCode':row['partCode'],
                     'calibratorVersion':None,'loadable':row['available'] is True}
                    for row in internal['models']]}
