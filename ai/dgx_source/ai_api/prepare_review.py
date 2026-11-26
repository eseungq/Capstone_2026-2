"""Build offline human-review workspace from existing diagnostic evidence; no GPU."""
import argparse
import csv
import hashlib
import html
import json
import math
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from ai_api.verify_gpu import ROOT,dump

USER_OBSERVATIONS={
    '204_101_20_5547e2eb-1df8-4a41-bbe9-97993888c9c9.jpg':'가로로 긴 긁힘을 후보 ②가 충분히 강조하지 못함',
    '204_101_20_197ee9cc-aeaa-44ed-b3ee-659b5caa487b.jpg':'후보 ②가 결함 주변 일부를 강조하지만 전체 손상 범위를 덮지는 못함',
}
Image.MAX_IMAGE_PIXELS=120_000_000

def orient_point(x,y,width,height,orientation):
    return {1:(x,y),2:(width-x,y),3:(width-x,height-y),4:(x,height-y),
            5:(y,x),6:(height-y,x),7:(height-y,width-x),8:(y,width-x)}[orientation]


def polygons(annotation):
    segmentation=annotation.get('segmentation')
    if isinstance(segmentation,list) and segmentation:
        parts=segmentation if isinstance(segmentation[0],list) else [segmentation]
        if all(len(p)>=6 and len(p)%2==0 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in p) for p in parts):
            return [[(p[i],p[i+1]) for i in range(0,len(p),2)] for p in parts],'segmentation'
    box=annotation.get('bbox')
    if isinstance(box,list) and len(box)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in box):
        x,y,w,h=box
        if w>0 and h>0:return [[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]],'bbox'
    return [],'unsupported'


def build(report_path):
    report_path=report_path.resolve();source=report_path.parent
    if not source.is_relative_to((ROOT/'ai_api/verification').resolve()):raise ValueError('Use an existing ai_api verification report')
    report=json.loads(report_path.read_text())
    output=ROOT/'ai_api/verification'/('review_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    with (ROOT/'outputs/manifests/door_internal_validation.csv').open(encoding='utf-8-sig') as f:
        internal={str(Path(r['image_path']).resolve()):r for r in csv.DictReader(f)}
    cases=[]
    for sample in report['samples']:
        path=Path(sample['imagePath']).resolve()
        if str(path) not in internal:raise ValueError('Sample outside internal validation')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sample['imageSha256']:raise ValueError('Image hash changed')
        ident=sample['id'];dest=output/ident;dest.mkdir()
        with Image.open(path) as source_image:
            orientation=source_image.getexif().get(274,1);raw_size=source_image.size
            original=ImageOps.exif_transpose(source_image).convert('RGB')
        original.thumbnail((1200,1200));original.save(dest/'original.jpg',quality=94)
        label_path=Path(internal[str(path)]['json_path']);label=json.loads(label_path.read_text(encoding='utf-8-sig'))
        label_images=label.get('images',[])
        metadata_match=len(label_images)==1 and (label_images[0].get('width'),label_images[0].get('height'))==raw_size
        overlay=original.copy();draw=ImageDraw.Draw(overlay);annotation_info=[]
        displayed=original.copy();display_draw=ImageDraw.Draw(displayed)
        display_size=sample['displaySize'];scale_x=original.width/display_size[0];scale_y=original.height/display_size[1]
        display_match=len(label_images)==1 and (label_images[0].get('width'),label_images[0].get('height'))==tuple(display_size)
        for a in label.get('annotations',[]):
            shapes,kind=polygons(a);annotation_info.append(dict(id=a.get('id'),type=kind,quality=a.get('attributes',{}).get('quality')))
            for shape in shapes:
                if metadata_match:
                    points=[orient_point(x,y,*raw_size,orientation) for x,y in shape]
                    points=[(x*scale_x,y*scale_y) for x,y in points]
                    draw.line(points+[points[0]],fill='#ffdf00',width=3)
                if display_match:
                    points=[(x*scale_x,y*scale_y) for x,y in shape]
                    display_draw.line(points+[points[0]],fill='#ffdf00',width=3)
        overlay.save(dest/'annotation.jpg',quality=94)
        displayed.save(dest/'annotation_display.jpg',quality=94)
        input_image=source/ident/'input224.png'
        if input_image.exists():
            with Image.open(input_image) as im:im.save(dest/'input224.png')
        layers=[]
        for layer in sample['layers']:
            copied=dict(layer);cam_path=source/ident/layer['slug']/'overlay.png'
            if layer['status']=='GENERATED' and cam_path.exists():
                with Image.open(cam_path) as im:
                    if im.size!=tuple(display_size):raise ValueError('CAM geometry mismatch')
                    preview=im.convert('RGB');preview.thumbnail((1200,1200));preview.save(dest/(layer['slug']+'.jpg'),quality=94)
                copied['preview']=ident+'/'+layer['slug']+'.jpg'
                copied['originalOverlay']=cam_path.as_uri()
            layers.append(copied)
        cases.append(dict(id=ident,imageName=path.name,savedKind=sample['savedKind'],score=sample.get('singleScore'),
                          originalUrl=path.as_uri(),annotationMetadataMatches=metadata_match,annotations=annotation_info,layers=layers,
                          annotationDisplayMetadataMatches=display_match,exifOrientation=orientation,
                          framingAssessment=sample.get('framingAssessment'),
                          userObservation=sample.get('priorUserNotes') or USER_OBSERVATIONS.get(path.name,''),
                          observationSource='사용자 스크린샷·관찰, 표시된 rawMax와 표본 기록 대조' if path.name in USER_OBSERVATIONS else '',
                          annotationCoordinateAssumption='Compare A: raw-before-EXIF coordinates versus B: display coordinates; neither automatically accepted'))
    manifest=dict(sourceReport=str(report_path),sourceReportSha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
                  finalTestUsed=False,modelChanged=False,serviceLayerChanged=False,cases=cases)
    dump(output/'review_manifest.json',manifest)
    page=Path(__file__).with_name('review_template.html').read_text()
    page=page.replace('__DATA__',json.dumps(manifest,ensure_ascii=False).replace('<','\\u003c'))
    (output/'index.html').write_text(page)
    (output/'NEXT_STEPS.md').write_text('1. index.html을 열어 원본과 JSON 주석을 먼저 확인합니다.\n2. 각 레이어의 결함 관련성·배경 반응·설명 유용성을 기록합니다.\n3. JSON 내보내기로 검토 기록을 저장합니다. 다시 열 때 가져오기를 사용합니다.\n4. 12장 검토 후 결함 관련성·오해 우려·0 맵을 함께 비교합니다. 생성률만으로 레이어를 선택하지 않습니다.\n5. 레이어 변경은 별도 검증 후 결정합니다. 재학습·해상도 변경은 이 검토의 결과를 근거로 별도 실험합니다.\n')
    print('[REVIEW READY]',output/'index.html')
    return output


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    build(args.report)


if __name__=='__main__':main()
