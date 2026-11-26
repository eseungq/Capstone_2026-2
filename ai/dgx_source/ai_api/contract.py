"""DEVELOPMENT PROPOSAL ONLY: replace this adapter after v4 fields are confirmed.

No backend AUTO_PASS/REVIEW policy is implemented here.
"""
from prototype.app import Problem

PROFILE = 'development-proposal-v4-pending'


class Failure(Problem):
    def __init__(self, code, status):
        super().__init__(code,status)
        self.code = code


def success(inspection_id, version, prediction, size, cam):
    return dict(inspectionId=inspection_id, modelVersion=version,
                predictedQuality='DEFECT' if prediction['predicted_class'] else 'GOOD',
                rawDefectProbability=prediction['raw_defect_score'],
                calibratedDefectProbability=None, calibratorVersion=None,
                imageWidth=size[0], imageHeight=size[1], gradcam=cam,
                inferenceTimeMs=prediction['processing_ms'])


def error(inspection_id, code):
    return dict(inspectionId=inspection_id, error=dict(code=code))


def gradcam(status, png=None, *, mime_type='image/png'):
    return dict(status=status, targetClass=1 if status!='NOT_GENERATED_GOOD' else None,
                mimeType=mime_type if png else None, base64=png)
