"""Local, read-only source-data inspection. This does not create training labels."""
import argparse
import io
import json
import math
import secrets
import threading
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw, ImageOps

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path('D:/162.부품 품질 검사 영상 데이터(자동차)/door_validation_extracted')
EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def as_list(value):
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, dict) else []


def polygons_from(value):
    """Return validated polygon coordinates; unsupported RLE is reported, not guessed."""
    if not value:
        return [], []
    if not isinstance(value, list):
        return [], ['폴리곤 이외의 segmentation 형식: 시각화 미지원']
    if value and isinstance(value[0], (int, float)):
        value = [value]
    polygons, issues = [], []
    for polygon in value:
        if (not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in polygon)):
            issues.append('잘못된 폴리곤 좌표')
        else:
            polygons.append(polygon)
    return polygons, issues


def patch_box(width, height, grid, index):
    if grid not in (1, 2, 3, 4) or not 0 <= index < grid * grid:
        raise ValueError('허용되지 않는 격자 또는 패치 번호')
    row, col = divmod(index, grid)
    return (col * width // grid, row * height // grid,
            (col + 1) * width // grid, (row + 1) * height // grid)


def patch_mask_count(polygons, box):
    """Union in the raw image coordinate system, clipped to one patch."""
    left, top, right, bottom = box
    mask = Image.new('1', (right - left, bottom - top))
    painter = ImageDraw.Draw(mask)
    for poly in polygons:
        points = [(poly[i] - left, poly[i + 1] - top) for i in range(0, len(poly), 2)]
        painter.polygon(points, fill=255)
    return mask.histogram()[255]


def patch_evidence(quality, mask_pixels):
    if mask_pixels:
        return '라벨 마스크와 겹침 — 결함이 보이는지 확인 필요'
    if quality == '양품':
        return '원본 양품 라벨 — 이 패치의 부품·배경 여부를 확인하세요'
    return '마스크와 겹치지 않음 — 정상 패치로 확정할 수 없음'


def validate_frame(item, mode):
    if mode not in ('stored', 'exif'):
        raise ValueError('알 수 없는 표시 방향')
    with Image.open(item['image_path']) as im:
        width, height = im.size
        if mode == 'exif' and im.getexif().get(274) in (5, 6, 7, 8):
            width, height = height, width
    if (width, height) != (item['width'], item['height']):
        raise ValueError('선택한 방향의 이미지 크기와 라벨 크기가 다릅니다. 좌표 기준 확인이 필요합니다.')


def frame_name(mode):
    return 'exif_transposed_pixels_json_unchanged' if mode == 'exif' else 'stored_pixels_no_exif_transpose'


def build_catalog(root):
    images_root, labels_root = root / 'images', root / 'labels'
    if not images_root.is_dir() or not labels_root.is_dir():
        raise FileNotFoundError(f'images와 labels 하위 폴더가 필요합니다: {root}')
    images = defaultdict(list)
    for path in images_root.rglob('*'):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            images[path.name.casefold()].append(path)
    items, failures = [], []
    for path in sorted(labels_root.rglob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            image_records = as_list(data.get('images'))
            if not image_records:
                raise ValueError('images가 비어 있음')
            categories = {str(c['id']): c.get('name', str(c['id'])) for c in as_list(data.get('categories'))}
            for record in image_records:
                filename = Path(record['file_name'].replace('\\', '/')).name
                matches = images.get(filename.casefold(), [])
                if len(matches) != 1:
                    raise ValueError(f'{filename}: 이미지 경로 {len(matches)}개 (자동 추정하지 않음)')
                annotations = [a for a in as_list(data.get('annotations'))
                               if a.get('image_id') == record.get('id')]
                quality = sorted({a.get('attributes', {}).get('quality', '미상') for a in annotations})
                issues, polygons, boxes = [], [], []
                if len(quality) != 1:
                    issues.append('판정 라벨 누락 또는 충돌')
                width, height = int(record['width']), int(record['height'])
                if width <= 0 or height <= 0:
                    raise ValueError('잘못된 이미지 크기')
                for annotation in annotations:
                    poly, problems = polygons_from(annotation.get('segmentation'))
                    polygons.extend(poly)
                    issues.extend(problems)
                    bbox = annotation.get('bbox')
                    if bbox is not None:
                        if (isinstance(bbox, list) and len(bbox) == 4
                                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in bbox)
                                and bbox[2] > 0 and bbox[3] > 0):
                            boxes.append(bbox)
                        else:
                            issues.append('잘못된 bbox')
                for poly in polygons:
                    if any(not 0 <= x <= width for x in poly[0::2]) or any(not 0 <= y <= height for y in poly[1::2]):
                        issues.append('폴리곤이 이미지 범위를 벗어남')
                with Image.open(matches[0]) as im:
                    actual_size = im.size
                    orientation = im.getexif().get(274, 1)
                if actual_size != (width, height):
                    issues.append(f'라벨 크기와 저장 이미지 크기 불일치: {actual_size}')
                items.append(dict(id=len(items), filename=filename, image_path=str(matches[0]),
                                  json_path=str(path), width=width, height=height,
                                  quality=quality[0] if len(quality) == 1 else '미상',
                                  categories=sorted({categories.get(str(a.get('category_id')), '미상') for a in annotations}),
                                  polygons=polygons, boxes=boxes, issues=sorted(set(issues)),
                                  orientation=orientation, annotation_count=len(annotations)))
        except Exception as exc:
            failures.append({'json_path': str(path), 'error': str(exc)})
    counts = Counter(item['quality'] for item in items)
    summary = dict(source_root=str(root), split='AI-Hub Validation (기존 최종 시험용)',
                   image_files=sum(map(len, images.values())), indexed_images=len(items),
                   quality_counts=dict(counts), polygon_images=sum(bool(i['polygons']) for i in items),
                   issue_images=sum(bool(i['issues']) for i in items), failures=failures,
                   issue_details=[{'filename': i['filename'], 'issues': i['issues']} for i in items if i['issues']],
                   exif_orientations=dict(Counter(str(i['orientation']) for i in items)),
                   purpose='라벨·좌표 점검만 수행. 학습/임계값/패치 설정 선택에 사용하지 않음.')
    return items, summary


def serve(items, summary, root, output, port, open_browser):
    token = secrets.token_urlsafe(24)
    session = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + secrets.token_hex(3)
    output.mkdir(parents=True, exist_ok=True)
    summary_path = output / f'{session}_inventory.json'
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    review_path = output / f'{session}_reviews.jsonl'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, content, mime='application/json', status=200):
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False).encode('utf-8')
            if isinstance(content, str):
                content = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith(('text/', 'application/json')) else ''))
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def get_item(self, params):
            index = int(params.get('id', ['-1'])[0])
            if not 0 <= index < len(items):
                raise ValueError('이미지 번호가 올바르지 않습니다')
            return items[index]

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == '/':
                    return self.respond((Path(__file__).with_name('door_patch_inspector.html')).read_text(encoding='utf-8'), 'text/html')
                if parsed.path == '/api/catalog':
                    brief = [{k: i[k] for k in ('id', 'filename', 'quality', 'categories', 'issues')}
                             | {'has_mask': bool(i['polygons'])} for i in items]
                    return self.respond(dict(items=brief, summary=summary, token=token, review_path=str(review_path)))
                if parsed.path == '/api/item':
                    return self.respond(self.get_item(params))
                if parsed.path in ('/api/image', '/api/patch'):
                    item = self.get_item(params)
                    mode = params.get('mode', ['stored'])[0]
                    validate_frame(item, mode)
                    with Image.open(item['image_path']) as im:
                        # Explicit display comparison; JSON coordinates are never edited.
                        # No training/application preprocessing policy is selected here.
                        if mode == 'exif':
                            im = ImageOps.exif_transpose(im)
                        if parsed.path == '/api/patch':
                            grid, index = int(params['grid'][0]), int(params['patch'][0])
                            box = patch_box(*im.size, grid, index)
                            preview = im.crop(box)
                        else:
                            im.draft('RGB', (1400, 1400))
                            preview = im.copy()
                        preview.thumbnail((1400, 1400))
                        buffer = io.BytesIO()
                        preview.convert('RGB').save(buffer, 'JPEG', quality=90)
                    return self.respond(buffer.getvalue(), 'image/jpeg')
                if parsed.path == '/api/evidence':
                    item = self.get_item(params)
                    validate_frame(item, params.get('mode', ['stored'])[0])
                    box = patch_box(item['width'], item['height'], int(params['grid'][0]), int(params['patch'][0]))
                    pixels = patch_mask_count(item['polygons'], box)
                    return self.respond(dict(box=box, mask_pixels=pixels,
                                             evidence=patch_evidence(item['quality'], pixels)))
                self.respond({'error': '경로 없음'}, status=404)
            except Exception as exc:
                self.respond({'error': str(exc)}, status=400)

        def do_POST(self):
            if self.path != '/api/review' or self.headers.get('X-Inspection-Token') != token:
                return self.respond({'error': '허용되지 않는 요청'}, status=403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16000:
                    raise ValueError('잘못된 요청 크기')
                data = json.loads(self.rfile.read(size))
                item = self.get_item({'id': [str(data['id'])]})
                mode = data.get('mode', 'stored')
                validate_frame(item, mode)
                grid, index = int(data['grid']), int(data['patch'])
                box = patch_box(item['width'], item['height'], grid, index)
                allowed = {'defect_visible', 'unclear', 'no_visible_defect', 'background'}
                if data['observation'] not in allowed:
                    raise ValueError('알 수 없는 확인 값')
                note = str(data.get('note', ''))[:2000]
                record = dict(timestamp=datetime.now(timezone.utc).isoformat(),
                              purpose='inspection_only_not_training_label', split=summary['split'],
                              image_path=item['image_path'], json_path=item['json_path'],
                              quality=item['quality'], grid=grid, patch_index=index,
                              box_xyxy=box, coordinate_frame=frame_name(mode), inspector_version=2,
                              mask_pixels=patch_mask_count(item['polygons'], box),
                              observation=data['observation'], note=note)
                with review_path.open('a', encoding='utf-8') as file:
                    file.write(json.dumps(record, ensure_ascii=False) + '\n')
                self.respond({'saved': True, 'path': str(review_path)})
            except Exception as exc:
                self.respond({'error': str(exc)}, status=400)

    server = HTTPServer(('127.0.0.1', port), Handler)
    address = f'http://127.0.0.1:{server.server_port}'
    print(f'점검 화면: {address}\n점검 기록: {review_path}\n종료: 이 창에서 Ctrl+C', flush=True)
    if open_browser:
        threading.Timer(1, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output', type=Path, default=PROJECT / 'outputs' / 'door_patch_inspection')
    parser.add_argument('--port', type=int, default=0, help='0: 사용 가능한 로컬 포트 자동 선택')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--scan-only', action='store_true')
    args = parser.parse_args()
    print(f'도어 라벨·이미지 확인 중: {args.data_root}', flush=True)
    items, summary = build_catalog(args.data_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if not items:
        raise SystemExit('연결 가능한 이미지가 없습니다. --data-root 경로를 확인하세요.')
    if not args.scan_only:
        serve(items, summary, args.data_root, args.output, args.port, not args.no_browser)


if __name__ == '__main__':
    main()
