"""Prepare observed-region pairs for full-framing FP/FP/FN diagnostic cases."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.verify_gpu import ROOT,dump


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    source=args.report.resolve()
    if not source.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Invalid source')
    report=json.loads(source.read_text());output=ROOT/'ai_api/verification'/('regions_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    cases=[]
    for s in report['samples']:
        if s['id'] not in ('sample_08','sample_09','sample_13'):continue
        path=Path(s['imagePath'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=s['imageSha256']:raise ValueError('Image changed')
        with Image.open(path) as original:im=ImageOps.exif_transpose(original).convert('RGB')
        im.thumbnail((1600,1600));im.save(output/(s['id']+'.jpg'),quality=96)
        cases.append(dict(id=s['id'],imageSha256=s['imageSha256'],savedKind=s['savedKind'],imageName=path.name,originalUrl=path.as_uri()))
    if len(cases)!=3:raise ValueError('Need three selected cases')
    payload=dict(schema='door-cam-regions-v2',sourceReport=str(source),sourceReportSha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=cases)
    dump(output/'source.json',payload)
    template=Path(__file__).with_name('regions_template.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')))
    print('[REGIONS READY]',output/'index.html')


if __name__=='__main__':main()
