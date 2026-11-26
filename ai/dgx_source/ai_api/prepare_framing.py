"""Offline framing scout + focused-case control inspection. No GPU or relabeling."""
import argparse
import hashlib
import json
import random
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps
from ai_api.diagnostics import ROOT,RUN,read,normalize_predictions
from ai_api.verify_gpu import dump


def pick(rows,excluded,seed=20261017):
    rng=random.Random(seed);chosen=[]
    for kind in ('TP','TN','FP','FN'):
        candidates=sorted([r for r in rows if r['kind']==kind and r['image_path'] not in excluded],key=lambda r:r['image_path'])
        if len(candidates)<4:raise ValueError('Insufficient unreviewed internal cases')
        rng.shuffle(candidates);chosen.extend(candidates[:4])
    return chosen


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--focused-report',type=Path,required=True)
    parser.add_argument('--reviews',type=Path,nargs='+',required=True);args=parser.parse_args()
    focused_path=args.focused_report.resolve();focused=json.loads(focused_path.read_text())
    if not focused_path.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Invalid focused report')
    output=ROOT/'ai_api/verification'/('framing_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    internal={r['image_path'] for r in read(ROOT/'outputs/manifests/door_internal_validation.csv')}
    prior={};review_sources=[]
    for path in args.reviews:
        exported=json.loads(path.read_text());source=Path(exported['sourceReport'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=exported['sourceReportSha256']:raise ValueError('Review source mismatch')
        report=json.loads(source.read_text());lookup={s['id']:s for s in report['samples']}
        for ident,review in exported['reviews'].items():
            sample=lookup[ident]
            if sample['imagePath'] not in internal:raise ValueError('Non-internal prior image')
            prior[sample['imagePath']]=dict(imagePath=sample['imagePath'],id=ident,sourceReport=str(source),framing=review.get('framing'),
                angle=review.get('angle'),originalVisibility=review.get('originalVisibility'),notes=review.get('notes',''),savedKind=sample['savedKind'])
        review_sources.append(dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    rows=normalize_predictions(read(RUN/'best_internal_validation_predictions.csv'))
    rows=[r for r in rows if r['image_path'] in internal];selected=pick(rows,set(prior))
    candidates=[]
    for i,row in enumerate(selected):
        path=Path(row['image_path']);ident=f'new_{i:02d}'
        with Image.open(path) as source:im=ImageOps.exif_transpose(source).convert('RGB')
        size=im.size;im.thumbnail((1200,1200));im.save(output/(ident+'.jpg'),quality=94)
        candidates.append(dict(id=ident,imageName=path.name,imagePath=str(path),originalUrl=path.as_uri(),imageSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               savedKind=row['kind'],displaySize=list(size)))
    roi=json.loads((focused_path.parent/'human_roi_original.json').read_text())
    source_report=json.loads(Path(roi['sourceReport']).read_text());sample=next(s for s in source_report['samples'] if s['id']=='sample_01')
    if sample['imagePath'] not in internal:raise ValueError('Non-internal focused case')
    with Image.open(sample['imagePath']) as source:im=ImageOps.exif_transpose(source).convert('RGB')
    im.thumbnail((1600,1600));im.save(output/'focus_original.jpg',quality=96)
    focus=next(s for s in focused['samples'] if s['id']=='sample_01')
    with Image.open(focused_path.parent/'sample_01/regions.png') as im:im.save(output/'focus_regions.png')
    region_details=[]
    with Image.open(focused_path.parent/'sample_01/input224.png') as im:
        for r in focus['regions']:
            if r['fill']!='mean':continue
            im.crop(tuple(r['box'])).save(output/('crop_'+r['name']+'.png'))
            region_details.append(dict(name=r['name'],box=r['box'],marginDropMean=r['drop']['margin'],
                marginDropBlur=next(x['drop']['margin'] for x in focus['regions'] if x['name']==r['name'] and x['fill']=='blur')))
    manifest=dict(schema='door-framing-scout-source-v1',finalTestUsed=False,training=False,modelChanged=False,labelsChanged=False,
                  focusedSource=str(focused_path),focusedSourceSha256=hashlib.sha256(focused_path.read_bytes()).hexdigest(),reviewSources=review_sources,
                  previous=list(prior.values()),candidates=candidates,focusImagePath=sample['imagePath'],focusOriginalUrl=Path(sample['imagePath']).as_uri(),regions=region_details,
                  selection='16 unreviewed internal cases, saved TP/TN/FP/FN x4, fixed seed; framing unconfirmed')
    dump(output/'source.json',manifest)
    template=Path(__file__).with_name('framing_template.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__',json.dumps(manifest,ensure_ascii=False).replace('<','\\u003c')))
    (output/'NEXT_STEPS.md').write_text('1. sample_01 영역 밖 결함·반사·구조물을 확인합니다. 비교 영역을 정상 영역이라고 가정하지 않습니다.\n2. 새 후보 16장은 촬영 구도와 도어 식별 가능 여부만 기록합니다. CAM 세 레이어 평가를 반복하지 않습니다.\n3. 전체 도어 사진이 없으면 억지로 전체로 분류하지 않습니다.\n4. JSON 내보내기로 저장한 후 구도별 사진 수를 확인해 다음 GPU 비교 표본을 고릅니다.\n5. 근접/전체 조건은 무작위 배정이 아니므로 촬영 구도의 인과 효과나 실제 공정 성능을 확정하지 않습니다.\n')
    print('[FRAMING REVIEW]',output/'index.html')


if __name__=='__main__':main()
