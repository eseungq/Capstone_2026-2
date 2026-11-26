"""Rank existing cross-split candidates using Pillow only; never relabel data."""
import argparse
import hashlib
import html
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def features(image):
    rgb = image.convert('RGB').resize((64, 64), Image.Resampling.LANCZOS)
    # Exclude FIND_EDGES boundary pixels, which otherwise inflate edge energy.
    edge = rgb.convert('L').filter(ImageFilter.FIND_EDGES).crop((1, 1, 63, 63))
    return rgb, edge, image.width / image.height


def metrics(a, b):
    rgb = sum(ImageStat.Stat(ImageChops.difference(a[0], b[0])).mean) / 3
    edge = ImageStat.Stat(ImageChops.difference(a[1], b[1])).mean[0]
    energy = (ImageStat.Stat(a[1]).mean[0] + ImageStat.Stat(b[1]).mean[0]) / 2
    relative_edge = edge / max(energy, 1.0)
    aspect = abs(a[2] - b[2]) / max(a[2], b[2])
    return dict(rgbMAE64=rgb, edgeMAE64=edge, edgeEnergy64=energy,
                relativeEdgeDifference=relative_edge, aspectDifference=aspect,
                rankScore=rgb/255 + relative_edge + aspect)


def load(path):
    try:
        with Image.open(path) as source:
            corrected = ImageOps.exif_transpose(source)
            return path, features(corrected), None
    except Exception as exc:
        return path, None, type(exc).__name__+': '+str(exc)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing audit_followup directory')
    args = parser.parse_args()
    source = args.source.resolve()
    candidate_file = source/'similarity_candidates.json'
    fingerprints = {r['image_path']: r for r in json.loads((source/'fingerprints.json').read_text())}
    pairs = [p for p in json.loads(candidate_file.read_text()) if not p['exact_bytes']]
    # Only the original train/internal whitelist can be opened.
    for p in pairs:
        if fingerprints[p['validation_image']]['split'] != 'internal_validation' or fingerprints[p['train_image']]['split'] != 'train':
            raise ValueError('Unexpected split in source candidates')
    output = ROOT/'ai_api/verification'/('similarity_rank_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir()
    report = dict(status='running', finalTestUsed=False, originalsModified=False,
                  source=str(source), sourceCandidateSHA256=hashlib.sha256(candidate_file.read_bytes()).hexdigest(),
                  scriptSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scoreDefinition='RGB MAE/255 + edge MAE/max(mean edge energy,1) + relative aspect difference; lower first',
                  limitations='Ranking heuristic only; low-detail images, crops, shifts and angle changes remain ambiguous; no identity threshold')
    dump(output/'summary.json', report)
    print('[RANK OUTPUT]', output, flush=True)
    try:
        paths = sorted({p[k] for p in pairs for k in ('validation_image','train_image')})
        cache, errors = {}, []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for i, (path, feature, error) in enumerate(pool.map(load, paths), 1):
                if error: errors.append(dict(path=path,error=error))
                else: cache[path]=feature
                if i%500==0 or i==len(paths): print('[FEATURES]',i,'/',len(paths),flush=True)
        ranked = []
        for p in pairs:
            if p['validation_image'] in cache and p['train_image'] in cache:
                ranked.append(dict(**p,**metrics(cache[p['validation_image']],cache[p['train_image']])))
        ranked.sort(key=lambda p:(p['rankScore'],p['validation_image'],p['train_image']))
        dump(output/'ranked_candidates.json',ranked)
        # One best match per validation image avoids repeated-photo dominance.
        seen, best = set(), []
        for p in ranked:
            if p['validation_image'] not in seen:
                best.append(p); seen.add(p['validation_image'])
        dump(output/'best_per_validation.json',best)
        parts=['<!doctype html><meta charset="utf-8"><title>유사 후보 재정렬</title><h1>유사 후보 재정렬</h1><p>색상·경계 구조·종횡비 차이가 작은 순서입니다. 검증 사진별 최상위 후보 중 상위50쌍입니다. 같은 사진·실물 또는 누수의 확정 판정이 아닙니다. 단색 영역의 오검출은 남을 수 있습니다.</p>']
        for i,p in enumerate(best[:50]):
            parts.append('<h2>후보 '+str(i+1)+'</h2><pre>'+html.escape(json.dumps(p,ensure_ascii=False,indent=2))+'</pre>')
            for side,key in [('valid','validation_image'),('train','train_image')]:
                with Image.open(p[key]) as original: image=ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((480,360));name=f'pair_{i:03d}_{side}.jpg';image.save(output/name,quality=88)
                parts.append(f'<img style="max-width:46%" src="{name}">')
        (output/'index.html').write_text('\n'.join(parts),encoding='utf-8')
        report.update(status='complete' if not errors else 'partial',sourcePairs=len(pairs),rankedPairs=len(ranked),
                      decodedImages=len(cache),errors=errors,validationImages=len(best),previewPairs=min(50,len(best)))
    except BaseException as exc:
        report.update(status='failed_or_interrupted',failure=repr(exc));raise
    finally:
        dump(output/'summary.json',report);print('[RANK REPORT]',output/'summary.json',flush=True)


if __name__ == '__main__':
    main()
