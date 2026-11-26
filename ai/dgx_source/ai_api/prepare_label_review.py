"""Prepare human label-conflict review without changing labels or splits."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from ai_api.prepare_review import orient_point, polygons

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'ai_api/verification/duplicate_groups_20261017T033939_279895Z/label_conflict_groups.json'


def main():
    groups=json.loads(SOURCE.read_text());rows={}
    for name in ['door_train.csv','door_internal_validation.csv']:
        with (ROOT/'outputs/manifests'/name).open(encoding='utf-8-sig') as stream:
            rows.update({r['image_path']:r for r in csv.DictReader(stream)})
    output=ROOT/'ai_api/verification'/('label_review_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));output.mkdir()
    cases=[]
    for i,group in enumerate(groups):
        if not all(p in rows for p in group['members']):raise ValueError('Unknown image')
        hashes={hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in group['members']}
        if len(hashes)!=1:raise ValueError('Expected byte-identical conflict group')
        representative=group['members'][0]
        with Image.open(representative) as source:
            raw_size=source.size;orientation=source.getexif().get(274,1)
            display=ImageOps.exif_transpose(source).convert('RGB')
        display_size=display.size;display.thumbnail((1400,1400))
        ident=f'case_{i:02d}';display.save(output/f'{ident}_original.jpg',quality=95)
        overlays=[display.copy(),display.copy()];sources=[]
        for path in group['members']:
            row=rows[path];label_path=Path(row['json_path']);label=json.loads(label_path.read_text(encoding='utf-8-sig'))
            size=(label['images'][0]['width'],label['images'][0]['height'])
            sources.append(dict(imagePath=path,jsonPath=str(label_path),jsonSHA256=hashlib.sha256(label_path.read_bytes()).hexdigest(),quality=row['quality'],categories=row['categories'],declaredSize=size))
            for a in label['annotations']:
                shapes,_=polygons(a)
                for points in shapes:
                    displayed=[(x*display.width/size[0],y*display.height/size[1]) for x,y in points]
                    raw=[orient_point(x*raw_size[0]/size[0],y*raw_size[1]/size[1],*raw_size,orientation) for x,y in points]
                    raw=[(x*display.width/display_size[0],y*display.height/display_size[1]) for x,y in raw]
                    for overlay,coords in zip(overlays,[displayed,raw]):ImageDraw.Draw(overlay).line(coords+[coords[0]],fill='red',width=3)
        for suffix,overlay in zip(['display','raw_exif'],overlays):overlay.save(output/f'{ident}_{suffix}.jpg',quality=95)
        cases.append(dict(id=ident,groupId=group['groupId'],representativeCandidate=representative,imageSHA256=next(iter(hashes)),originalUrl=Path(representative).as_uri(),rawSize=raw_size,displaySize=display_size,exif=orientation,sources=sources))
    data=dict(schema='door-label-conflict-review-v1',source=str(SOURCE),sourceSHA256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),rulesVersion='image-any-target-defect-proposal-v1',originalsModified=False,cases=cases)
    (output/'source.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    template=Path(__file__).with_name('label_review_template.html').read_text()
    (output/'index.html').write_text(template.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c')))
    print('[LABEL REVIEW READY]',output/'index.html')


if __name__=='__main__':main()
