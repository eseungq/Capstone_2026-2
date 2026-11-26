"""Freeze diagnostic samples without reading calibration, policy, or final-test images."""
import ast
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageOps

ROOT = Path('/path/to/private/validated-project')
SEED = '20261104-cam-followup-v1'
RUN = ROOT / 'outputs/door_next_training/door_visible_20261029_162657_477520'
SOURCE = ROOT / 'outputs/door_next_review/20261030T020059_489653Z/report.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

def fingerprints(image):
    grey = image.convert('L')
    pixels = list(grey.resize((9, 8), Image.Resampling.BILINEAR).getdata())
    dhash = sum(int(pixels[y*9+x] > pixels[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))
    small = list(grey.resize((8, 8), Image.Resampling.BILINEAR).getdata())
    average = sum(small) / len(small)
    ahash = sum(int(value >= average) << index for index, value in enumerate(small))
    return dhash, ahash

def main():
    Image.MAX_IMAGE_PIXELS = 120000000
    run_config = json.loads((RUN / 'run_config.json').read_text())
    candidate = json.loads((ROOT / 'ai_api/door_e02_candidate.json').read_text())
    assert sha(RUN / 'best.pt') == candidate['checkpointSHA256']
    assert sha(SOURCE) == candidate['sourceReviewSHA256']
    previous = json.loads(SOURCE.read_text())['samples']
    extra = candidate['samples']
    excluded = {row['image_path'] for row in previous + extra}
    manifest_path = RUN / 'model_selection_used.csv'
    predictions_path = RUN / 'best_model_selection_predictions.csv'
    manifest = {row['image_path']: row for row in load_csv(manifest_path)}
    excluded_groups = {manifest[path]['group_id'] for path in excluded if path in manifest}
    used_hashes = set()
    previous_fingerprints = []
    for path in sorted(excluded):
        image_path = Path(path)
        used_hashes.add(sha(image_path))
        with Image.open(image_path) as image:
            previous_fingerprints.append(fingerprints(ImageOps.exif_transpose(image)))
    predictions = load_csv(predictions_path)
    assert len(predictions) == len(manifest) == 1959
    pool = []
    for prediction in predictions:
        path = prediction['image_path']
        row = manifest[path]
        if path in excluded or row['group_id'] in excluded_groups or prediction['correct'] != '1':
            continue
        assert int(row['class_id']) == int(prediction['class_id'])
        assert row['future_split'] == 'model_selection'
        ratio = float(row['width']) / float(row['height'])
        bucket = 'portrait_square' if ratio < 1.4 else ('landscape' if ratio < 2.1 else 'wide')
        score = float(prediction['raw_defect_score'])
        pool.append(dict(prediction, **{key: row[key] for key in ('group_id', 'json_path', 'source_categories', 'label_basis')}, aspectBucket=bucket, scoreBand='near_cutoff' if score < .9 else 'high'))
    output = ROOT / 'outputs/door_e02_live/cam_followup_20261104' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True, exist_ok=False)
    chosen = []
    selected_fingerprints = []
    selected_groups = set()
    rejections = []
    # Fixed strata are chosen before observing any new CAM. Scores are stored GPU batch scores.
    strata = [(1, category, aspect, band) for category in ('스크래치', '외관 손상') for aspect in ('portrait_square', 'landscape', 'wide') for band in ('near_cutoff', 'high')]
    strata += [(0, category, aspect, None) for category in ('스크래치', '외관 손상') for aspect in ('portrait_square', 'landscape', 'wide')]
    for class_id, category, aspect, band in strata:
        candidates = [row for row in pool if int(row['class_id']) == class_id and row['source_categories'] == category and row['aspectBucket'] == aspect and (band is None or row['scoreBand'] == band)]
        candidates.sort(key=lambda row: hashlib.sha256((SEED + '|' + row['image_path']).encode()).hexdigest())
        picked = None
        for row in candidates:
            path = Path(row['image_path'])
            if row['group_id'] in selected_groups:
                continue
            digest = sha(path)
            if digest in used_hashes:
                rejections.append(dict(path=str(path), reason='exact_image_hash'))
                continue
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert('RGB')
                fp = fingerprints(image)
                matches = [(left ^ fp[0]).bit_count() <= 3 and (right ^ fp[1]).bit_count() <= 3 for left, right in previous_fingerprints + selected_fingerprints]
                if any(matches):
                    rejections.append(dict(path=str(path), reason='both_ahash_and_dhash_distance_le_3_diversity_filter'))
                    continue
                sid = f'followup_{len(chosen)+1:02d}'
                target = output / sid
                target.mkdir()
                display = image.copy()
                display.thumbnail((1400, 1000))
                display.save(target / 'original.jpg', quality=92)
                ImageOps.pad(image, (224,224), method=Image.Resampling.BICUBIC, color=(124,116,104)).save(target / 'input224.png')
                picked = dict(row, id=sid, imageSHA256=digest, displaySize=list(image.size), savedKind='TP' if class_id else 'TN', originalLabelChanged=False)
            chosen.append(picked)
            selected_groups.add(row['group_id'])
            selected_fingerprints.append(fp)
            used_hashes.add(digest)
            print('SELECTED',sid,picked['savedKind'],category,aspect,band,flush=True)
            break
        if picked is None:
            raise RuntimeError('Fixed stratum has no eligible sample: '+repr((class_id,category,aspect,band)))
    assert len(chosen) == 18 and len(selected_groups) == 18
    data = dict(schema='cam-followup-fixed-samples-v1', output=str(output), modelVersion=candidate['modelVersion'], checkpointSHA256=candidate['checkpointSHA256'], manifestSHA256=sha(manifest_path), predictionsSHA256=sha(predictions_path), expectedVersions=run_config['versions'], seed=SEED, counts=dict(TP=12,TN=6), layers=['layers.3.blocks.1.norm1','layers.2.blocks.5.norm1'], objective='DEFECT logit', samples=chosen, exclusions=rejections, exclusionRules='Exclude previous 49+integration fixtures, their existing group IDs, exact selected/excluded image hashes, and pairs with both aHash and dHash distance <=3 for diagnostic diversity only. Not independence certification.', samplingWarning='Purposeful diagnostic strata; neither population accuracy nor independent final evaluation. Source categories on GOOD images are inspection categories, not defect labels.', finalTestImagesRead=False, calibrationOrPolicyImagesRead=False, humanAssessmentPending=True, modelOrThresholdChanged=False)
    (output/'selection.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    pointer = ROOT / 'ai_api/cam_followup_20261104/latest.json'
    pointer.write_text(json.dumps(dict(output=str(output),selectionSHA256=sha(output/'selection.json')),indent=2)+'\n')
    print('FROZEN',str(output),sha(output/'selection.json'),flush=True)

if __name__ == '__main__':
    main()
