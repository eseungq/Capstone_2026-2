"""Prepare three-case human ROI selection, without model execution."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.verify_gpu import ROOT,dump


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    report_path=args.report.resolve();report=json.loads(report_path.read_text())
    if not report_path.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Invalid source')
    output=ROOT/'ai_api/verification'/('roi_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    selected=[]
    for sample in report['samples']:
        if sample['id'] not in ('sample_00','sample_01','sample_02'):continue
        if sample['savedKind']!='TP':raise ValueError('Selected case is not TP')
        path=Path(sample['imagePath'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sample['imageSha256']:raise ValueError('Image changed')
        with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGB')
        im.thumbnail((1600,1600));im.save(output/(sample['id']+'.jpg'),quality=96)
        selected.append(dict(id=sample['id'],imageSha256=sample['imageSha256'],imageName=path.name))
    if len(selected)!=3:raise ValueError('Need three cases')
    payload=dict(schema='door-cam-roi-v1',sourceReport=str(report_path),sourceReportSha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),cases=selected)
    dump(output/'source.json',payload)
    template=Path(__file__).with_name('roi_template.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')))
    print('[ROI READY]',output/'index.html')


if __name__=='__main__':main()
