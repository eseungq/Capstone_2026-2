"""Non-active internal response drafts: S2 payload names + S4 semantics.

Returns a draft and unresolved decisions, NEVER rewrites Service responses.
No policy, new state enum, or final-contract claim is implemented here.
"""
from copy import deepcopy


def candidate(response):
    draft=deepcopy(response);cam=draft.pop('gradcam')
    state=cam['status'];questions=['Exact JSON placement of gradcamStatus requires backend confirmation']
    if state=='NOT_GENERATED_GOOD':status='NOT_REQUIRED';target=None;image=None
    elif state=='GENERATED':status='GENERATED';target='DEFECT';image=cam['base64']
    elif state=='FAILED':status='FAILED';target='DEFECT';image=None
    elif state in ['ZERO_MAP','CONSTANT_MAP']:
        status=None;target='DEFECT';image=None
        questions.append('Successful zero/constant map: confirm allowed existing status and null image; no invented enum or failure mapping')
    else:raise ValueError('Unknown internal CAM computation state')
    draft['gradcam']={'targetClass':target,'format':'png' if image else None,'imageBase64':image}
    return {'scope':'inactive_internal_contract_candidate','responseDraftWithoutStatusPlacement':draft,'agreedStatusToPlace':status,'internalComputationState':state,'unresolved':questions,'activated':False}
