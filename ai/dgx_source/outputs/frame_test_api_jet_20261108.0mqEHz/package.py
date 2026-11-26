import base64
import hashlib
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0, '/path/to/private/validated-project/outputs/frame_test_api_jet_20261108.0mqEHz')
from frame_unified_test_api_20261107 import FRAME_SHA256, CAM_LAYER, MODEL_VERSION, create_engine, load_shared_api, new_server, request, running

root, out = map(Path, sys.argv[1:])
out.mkdir()
load_shared_api(root, out)
engine = create_engine(root)
photos, evidence = {}, {}
for role, review, ident, label in (
    ('normal', '20261026T144548_871522Z', '11', 'GOOD'),
    ('defect', '20261026T173009_535686Z', '06', 'DEFECT'),
    ('backup', '20261026T173009_535686Z', '15', 'DEFECT'),
):
    folder = root / 'outputs/frame_cam_review' / review
    selection = json.loads((folder / 'selection.json').read_text())
    if selection['checkpoints']['unified']['sha256'] != FRAME_SHA256:
        raise ValueError('Checkpoint mismatch')
    row = next(item['source'] for item in selection['items'] if item['id'] == ident)
    with open(row['image_archive'], 'rb') as archive:
        blob = os.pread(archive.fileno(), int(row['size']), int(row['offset']))
    digest = hashlib.sha256(blob).hexdigest()
    if digest != row['image_sha256'] or label != ('DEFECT' if int(row['class_id']) else 'GOOD'):
        raise ValueError('Fixture changed')
    photos[role] = blob
    evidence[role] = dict(review=review, sample=ident, inspectionType=row['defect_type'], label=label,
                          imageSHA256=digest, original=f'{role}.jpg')

class Origin(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def do_GET(self):
        blob = photos.get(self.path.removeprefix('/'))
        if blob is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'image/jpeg')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

with running(ThreadingHTTPServer(('127.0.0.1', 0), Origin)) as origin:
    with running(new_server(('127.0.0.1', 0), engine, [origin], out / 'requests')) as api:
        for role, row in evidence.items():
            status, body, headers = request(api + '/internal/v1/predict', dict(
                inspectionId=f'frame-demo-{role}', partCode='FRAME', requestedModelVersion=MODEL_VERSION,
                imageUrl=f'{origin}/{role}',
            ))
            if status != 200 or body['predictedQuality'] != row['label'] or body['modelVersion'] != MODEL_VERSION:
                raise RuntimeError(f'FRAME prediction failed for {role}')
            if (body['calibratedDefectProbability'], body['calibratorVersion']) != (None, None):
                raise ValueError('Unexpected calibration')
            cam = body['gradcam']
            if row['label'] == 'GOOD':
                if cam is not None:
                    raise ValueError('GOOD unexpectedly returned CAM')
            else:
                if (cam['status'], cam['format'], cam['targetClass']) != ('GENERATED', 'jpeg', 'DEFECT'):
                    raise ValueError('Expected a DEFECT JPEG')
                binary = base64.b64decode(cam['imageBase64'], validate=True)
                with Image.open(io.BytesIO(photos[role])) as original, Image.open(io.BytesIO(binary)) as overlay:
                    if overlay.format != 'JPEG' or overlay.size != ImageOps.exif_transpose(original).size:
                        raise ValueError('Unexpected CAM encoding or size')
                    overlay.verify()
                row['cam'] = f'{role}_cam.jpg'
                (out / row['cam']).write_bytes(binary)
            (out / row['original']).write_bytes(photos[role])
            row.update(prediction=body['predictedQuality'], rawDefectProbability=body['rawDefectProbability'],
                       inferenceTimeMs=body['inferenceTimeMs'], traceId=headers['X-Trace-Id'])
report = dict(modelVersion=MODEL_VERSION, checkpointSHA256=FRAME_SHA256, camLayer=CAM_LAYER, camPalette="JET", camAlpha=0.5,
              scope='DGX GPU loopback HTTP, previously reviewed fixtures', samples=evidence)
serialized = json.dumps(report, ensure_ascii=False, indent=2)
(out / 'report.json').write_text(serialized + '\n')
print(serialized)

