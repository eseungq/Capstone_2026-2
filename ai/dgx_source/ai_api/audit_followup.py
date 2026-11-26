"""Read-only coordinate hypotheses and full train/internal cross-split dHash scan."""
import csv
import html
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from ai_api.audit_data import difference_hash

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ai_api/verification/data_audit_20261016T181906_711013Z'


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def preview(image, boxes, size, path):
    image = image.copy()
    image.thumbnail((640, 480))
    draw = ImageDraw.Draw(image)
    for x, y, w, h in boxes:
        sx, sy = image.width / size[0], image.height / size[1]
        draw.rectangle((x*sx, y*sy, (x+w)*sx, (y+h)*sy), outline='red', width=2)
    image.save(path, quality=88)


def coordinates(output):
    records = json.loads((SOURCE/'priority_review/coordinate_evidence.json').read_text())['records']
    parts = ['<!doctype html><meta charset="utf-8"><title>좌표 가설 비교</title>',
             '<h1>28장 좌표 가설 비교</h1><p>빨간 사각형은 원본 주석의 변환 가설입니다. 결함의 정답 위치로 확정하지 않았습니다. 원본과 주석은 변경하지 않았습니다.</p>']
    selected = [r for r in records if not r['display_size_matches']]
    for i, r in enumerate(selected):
        with Image.open(r['image_path']) as source:
            raw = source.convert('RGB')
            display = ImageOps.exif_transpose(source).convert('RGB')
            # Convert an annotation plane from declared size to raw pixels,
            # then apply the source EXIF transform. Diagnostic only.
            plane = Image.new('RGB', raw.size, 'black')
            draw = ImageDraw.Draw(plane)
            for x, y, w, h in r['bbox']:
                sx, sy = raw.width/r['declared_size'][0], raw.height/r['declared_size'][1]
                draw.rectangle((x*sx, y*sy, (x+w)*sx, (y+h)*sy), outline='red', width=max(2, raw.width//320))
            plane.getexif()[274] = r['exif']
            plane = ImageOps.exif_transpose(plane)
        prefix = f'coordinate_{i:02d}'
        preview(display, [], display.size, output/f'{prefix}_original.jpg')
        preview(display, r['bbox'], display.size, output/f'{prefix}_unchanged.jpg')
        preview(display, r['bbox'], r['declared_size'], output/f'{prefix}_display_scaled.jpg')
        composite = display.copy()
        composite.paste(plane, (0, 0), plane.convert('L').point(lambda v: 255 if v else 0))
        preview(composite, [], display.size, output/f'{prefix}_raw_scaled_exif.jpg')
        parts.append('<h2>'+str(i+1)+'</h2><pre>'+html.escape(json.dumps(r, ensure_ascii=False, indent=2))+'</pre>')
        for suffix, title in [('original','EXIF 보정 원본'), ('unchanged','좌표를 표시 이미지에 그대로 적용'),
                              ('display_scaled','JSON 크기 → 표시 크기 비례 변환 가설'),
                              ('raw_scaled_exif','JSON 크기 → 원본 픽셀 비례 변환 → EXIF 가설')]:
            parts.append(f'<figure style="display:inline-block;width:46%;vertical-align:top"><figcaption>{title}</figcaption><img style="max-width:100%" src="{prefix}_{suffix}.jpg"></figure>')
    (output/'coordinates.html').write_text('\n'.join(parts), encoding='utf-8')
    return len(selected)


def fingerprint(row):
    try:
        with Image.open(row['image_path']) as image:
            corrected = ImageOps.exif_transpose(image)
            digest = difference_hash(corrected)
        return dict(**row, dhash=digest)
    except Exception as exc:
        return dict(**row, error=type(exc).__name__+': '+str(exc))


def main():
    output = ROOT/'ai_api/verification'/('audit_followup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir()
    report = dict(status='running', finalTestUsed=False, originalsModified=False,
                  scope='full train/internal cross-split 64-bit dHash distance <=8; within-split not scanned',
                  limitations='Candidates only; no guarantee for crops, rotations, changed angles or same physical parts')
    dump(output/'summary.json', report)
    print('[FOLLOWUP OUTPUT]', output, flush=True)
    try:
        report['coordinateCases'] = coordinates(output)
        with (SOURCE/'image_hashes.csv').open(encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        assert Counter(r['split'] for r in rows) == {'train':11554,'internal_validation':2039}
        fingerprints = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, row in enumerate(pool.map(fingerprint, rows), 1):
                fingerprints.append(row)
                if i % 500 == 0 or i == len(rows):
                    print('[FINGERPRINT]', i, '/', len(rows), flush=True)
        dump(output/'fingerprints.json', fingerprints)
        train = [r for r in fingerprints if r['split']=='train' and 'dhash' in r]
        valid = [r for r in fingerprints if r['split']=='internal_validation' and 'dhash' in r]
        pairs = []
        for a in valid:
            for b in train:
                distance = (a['dhash'] ^ b['dhash']).bit_count()
                if distance <= 8:
                    pairs.append(dict(distance=distance, exact_bytes=a['sha256']==b['sha256'],
                                      validation_image=a['image_path'], train_image=b['image_path']))
        pairs.sort(key=lambda p:(p['exact_bytes'],p['distance'],p['validation_image'],p['train_image']))
        dump(output/'similarity_candidates.json', pairs)
        parts = ['<!doctype html><meta charset="utf-8"><title>유사 사진 후보</title><h1>유사 사진 후보</h1><p>거리는 64비트 dHash 기준입니다. 유사도는 동일 실물이나 누수의 확정 근거가 아닙니다. 전체 후보는 JSON, 이 화면은 정확 바이트 중복을 제외한 거리순 상위100쌍입니다.</p>']
        for i, pair in enumerate([p for p in pairs if not p['exact_bytes']][:100]):
            parts.append('<h2>후보 '+str(i+1)+'</h2><pre>'+html.escape(json.dumps(pair, ensure_ascii=False, indent=2))+'</pre>')
            for side, key in [('valid','validation_image'),('train','train_image')]:
                with Image.open(pair[key]) as source: image=ImageOps.exif_transpose(source).convert('RGB')
                name=f'pair_{i:03d}_{side}.jpg'; preview(image, [], image.size, output/name)
                parts.append(f'<img style="max-width:46%" src="{name}">')
        (output/'similarity.html').write_text('\n'.join(parts), encoding='utf-8')
        report.update(status='complete', fingerprinted=len(train)+len(valid),
                      errors=[r for r in fingerprints if 'error' in r], candidatePairs=len(pairs),
                      exactBytePairs=sum(p['exact_bytes'] for p in pairs),
                      nonExactCandidatePairs=sum(not p['exact_bytes'] for p in pairs),
                      comparedPairs=len(train)*len(valid))
    except BaseException as exc:
        report.update(status='failed_or_interrupted', failure=repr(exc)); raise
    finally:
        dump(output/'summary.json', report)
        print('[FOLLOWUP REPORT]', output/'summary.json', flush=True)


if __name__ == '__main__':
    main()
