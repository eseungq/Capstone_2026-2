from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from PIL import Image
import ast
import hashlib
import html
import json
import math
import shutil
import struct
import zipfile

root = Path('/path/to/private/validated-project')
source = root / 'outputs/door_next_review/20261030T020059_489653Z'
report_path = source / 'report.json'
assert hashlib.sha256(report_path.read_bytes()).hexdigest() == '6ccea764f5c7efb445eed8dece6d0f68943dc48e0ae29682f07696f2fdf342fb'
report = json.loads(report_path.read_text())
assert report['epoch'] == 2 and report['state_unchanged'] and not report['final_test_read']
observations = json.loads((root / 'outputs/door_cam_observation_import/20261030T025155_003430Z/observations.json').read_text())
notes = {item['id']: item for item in observations}
decisions = json.loads((root / 'outputs/door_label_recheck_import/20261030T031418_002483Z/image_decisions.json').read_text())
latest = {item['sampleId']: item for item in decisions}
links = json.loads((root / 'outputs/door_cam_observation_import/20261030T025155_003430Z/confirmed_within_validation_photo_links.json').read_text())
output = root / 'outputs/cam_comparison49' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
output.mkdir(parents=True)
Image.MAX_IMAGE_PIXELS = 120000000
rows = []
names = {'candidate_only': '후보만 유용', 'current_only': '기존만 유용', 'both_useful': '둘 다 유용', 'neither_useful': '둘 다 부적절', 'free_text_only': '자유 서술: 수치화 제외'}
parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>49장 CAM 비교</title><style>body{font-family:Malgun Gothic,sans-serif;max-width:1500px;margin:24px auto;padding:0 20px;background:#f4f7fa}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}figure{margin:0;border:1px solid #ccd}img{width:100%}figcaption{padding:10px}section{padding:20px;margin:24px 0;background:white}.note{white-space:pre-wrap;padding:12px;background:#edf2f7}p{line-height:1.8}</style><h1>동일 e02 모델의 기존 49장 GPU CAM 비교</h1><p>기존 사용자 판단을 재사용했습니다. 오판45건을 포함한 편향 표본이며 전체 위치 정확도나 독립 평가가 아닙니다. GOOD 예측의 CAM은 진단용입니다.</p>']

def read_map(path):
    with path.open('rb') as stream:
        assert stream.read(6) == b'\x93NUMPY'
        version = stream.read(2)
        fmt = '<H' if version[0] == 1 else '<I'
        length = struct.unpack(fmt, stream.read(struct.calcsize(fmt)))[0]
        header = ast.literal_eval(stream.read(length).decode('latin1').strip())
        data = stream.read()
    assert header['descr'] in ('<f4', '=f4') and not header['fortran_order']
    values = struct.unpack('<' + 'f' * math.prod(header['shape']), data)
    assert all(math.isfinite(value) for value in values)
    return header['shape'], min(values), max(values)

for sample in report['samples']:
    sid = sample['id']
    note = notes[sid]
    assert hashlib.sha256(Path(sample['image_path']).read_bytes()).hexdigest() == sample['image_sha256']
    source_case = source / sid
    target = output / sid
    target.mkdir()
    for layer, shape in [('layers.3.blocks.1.norm1', (7, 7)), ('layers.2.blocks.5.norm1', (14, 14))]:
        actual_shape, minimum, maximum = read_map(source_case / layer / 'raw.npy')
        assert actual_shape == shape
        expected = next(item for item in sample['layers'] if item['layer'] == layer)
        assert math.isclose(minimum, expected['rawMin'], abs_tol=1e-12)
        assert math.isclose(maximum, expected['rawMax'], abs_tol=1e-12)
    pair = (note.get('layer3_usefulness'), note.get('layer2_usefulness'))
    category = {('X', 'O'): 'candidate_only', ('O', 'X'): 'current_only', ('O', 'O'): 'both_useful', ('X', 'X'): 'neither_useful'}.get(pair, 'free_text_only')
    same = []
    for link in links:
        pair_ids = [link['sourceCase'], link['referenceCase']]
        if sid in pair_ids:
            same.extend(pair_ids)
    row = dict(id=sid, savedKind=sample['kind'], comparison=category, notes=note['raw_notes'], correction=note.get('layer_judgment_correction'), latestDecision=latest.get(sid), samePhotoCases=sorted(set(same)))
    rows.append(row)
    parts.append('<section><h2>' + sid + ' / 저장 분류 ' + sample['kind'] + ' / ' + names[category] + '</h2>')
    if sample['kind'] in ('TN', 'FN'):
        parts.append('<p>GOOD 예측: 아래 CAM은 진단 전용이며 앱에는 제공하지 않습니다.</p>')
    if same:
        parts.append('<p>사용자 확인 동일 사진: ' + ', '.join(sorted(set(same))) + '</p>')
    if sid in latest:
        decision = latest[sid]
        parts.append('<p>최신 라벨 재확인: ' + html.escape(decision['decision'] + ' / ' + decision['reason']) + ' — 원천 라벨·기존 지표는 변경하지 않음.</p>')
    parts.append('<div class="grid">')
    assets = [('display.jpg', 'original.jpg', '원본 표시'), ('input224.png', 'input224.png', '224 입력'), ('layers.3.blocks.1.norm1/overlay.png', 'current.jpg', '현재 7×7'), ('layers.2.blocks.5.norm1/overlay.png', 'candidate.jpg', '후보 14×14')]
    for filename, destname, label in assets:
        with Image.open(source_case / filename) as image:
            if 'overlay' in filename:
                assert list(image.size) == sample['display_size']
            if destname.endswith('.png'):
                shutil.copyfile(source_case / filename, target / destname)
            else:
                image = image.convert('RGB')
                image.thumbnail((900, 700), Image.Resampling.LANCZOS)
                image.save(target / destname, quality=88)
        asset = sid + '/' + destname
        parts.append('<figure><a href="' + asset + '"><img loading="lazy" src="' + asset + '"></a><figcaption>' + label + '</figcaption></figure>')
    parts.append('</div><p class="note">기존 메모: ' + html.escape(note['raw_notes']) + '</p>')
    if row['correction']:
        parts.append('<p>후속 정정: ' + html.escape(str(row['correction'])) + '</p>')
    parts.append('</section>')
    print('[49 CASE]', sid, category, flush=True)

counts = Counter(row['comparison'] for row in rows)
assert counts == Counter(candidate_only=7, current_only=5, both_useful=2, neither_useful=21, free_text_only=14)
service = [row for row in rows if row['savedKind'] in ('TP', 'FP')]
summary = dict(status='verified_saved_gpu_maps_and_existing_user_judgments', cases=49, rawMapsVerified=98, comparisonCounts=dict(counts), explicitPairedCases=35, freeTextOnly=14, savedConfusionCounts=dict(Counter(row['savedKind'] for row in rows)), serviceEligibleCases=len(service), serviceEligibleCounts=dict(Counter(row['comparison'] for row in service)), knownSamePhotoPairs=2, knownPhotoGroups=47, savedTPCases=2, savedTPKnownGroups=1, checkpointSHA256=report['checkpoint_sha256'], operatingLayerChanged=False, modelChanged=False, newInferencePerformed=False, finalTestRead=False, independentPerformanceEvaluation=False)
parts.insert(1, '<p>명시적 O/X 35건: 후보만 유용7 / 기존만 유용5 / 둘 다 유용2 / 둘 다 부적절21. 자유 서술14건은 임의 수치화하지 않았습니다. 정분류 불량2건은 동일 사진1그룹이므로, 이 자료만으로 후보 일괄 교체를 추천하지 않습니다.</p>')
parts.append('</html>')
(output / 'index.html').write_text('\n'.join(parts))
(output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
(output / 'comparison.json').write_text(json.dumps(dict(summary=summary, cases=rows), ensure_ascii=False, indent=2) + '\n')
(output / 'FINDINGS_KO.md').write_text('# 기존49장 비교 결과\n\n후보만 유용7·기존만 유용5·둘 다 유용2·둘 다 부적절21·자유 서술14. 오판 중심 표본이며 정분류 불량2건은 동일 사진1그룹입니다. 전체 위치 정확도·독립 성능 평가가 아닙니다. 운영 설정과 원본은 변경하지 않았습니다.\n')
(root / 'ai_api/e02_integration/latest_comparison49.json').write_text(json.dumps(dict(directory=str(output)), indent=2) + '\n')
with zipfile.ZipFile(output / 'CAM_49_comparison.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in output.rglob('*'):
        if path.is_file() and path.name != 'CAM_49_comparison.zip':
            archive.write(path, path.relative_to(output))
print('COMPLETED', output, flush=True)
print(json.dumps(summary, ensure_ascii=False), flush=True)
