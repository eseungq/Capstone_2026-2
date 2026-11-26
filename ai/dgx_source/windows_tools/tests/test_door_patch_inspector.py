import importlib.util
import json
import tempfile
import unittest
import subprocess
import sys
import io
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
from PIL import Image

spec = importlib.util.spec_from_file_location('inspector', Path(__file__).resolve().parents[1] / 'scripts/door_patch_inspector.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


class InspectorTests(unittest.TestCase):
    def test_grid_covers_odd_dimensions_once(self):
        boxes = [inspector.patch_box(13, 11, 3, i) for i in range(9)]
        pixels = [(x, y) for l, t, r, b in boxes for x in range(l, r) for y in range(t, b)]
        self.assertEqual(len(pixels), 143)
        self.assertEqual(len(set(pixels)), 143)

    def test_overlapping_masks_use_union_and_clip(self):
        polys = [[1, 1, 4, 1, 4, 4, 1, 4], [3, 1, 6, 1, 6, 4, 3, 4]]
        self.assertEqual(inspector.patch_mask_count(polys, (0, 0, 10, 10)), 24)
        self.assertEqual(inspector.patch_mask_count(polys, (5, 0, 10, 10)), 8)
        self.assertEqual(inspector.patch_mask_count(polys, (7, 0, 10, 10)), 0)

    def test_missing_mask_not_negative_label(self):
        self.assertIn('정상 패치로 확정할 수 없음', inspector.patch_evidence('불량품', 0))
        self.assertIn('부품·배경', inspector.patch_evidence('양품', 0))

    def test_bad_polygon_reported(self):
        polygons, issues = inspector.polygons_from([[1, 2, 3], [0, 0, 3, 0, 3, 4]])
        self.assertEqual(len(polygons), 1)
        self.assertEqual(len(issues), 1)
        self.assertTrue(inspector.polygons_from({'counts': 'abc'})[1])

    def test_catalog_bom_matching_annotations_and_exif(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'images').mkdir()
            (root / 'labels').mkdir()
            exif = Image.Exif()
            exif[274] = 6
            Image.new('RGB', (20, 10)).save(root / 'images' / 'sample.JPG', exif=exif)
            data = {'images': {'id': 1, 'file_name': 'sample.JPG', 'width': 20, 'height': 10},
                    'annotations': [{'image_id': 1, 'category_id': 101, 'attributes': {'quality': '불량품'},
                                     'segmentation': [[1, 1, 5, 1, 5, 5]]},
                                    {'image_id': 2, 'category_id': 102, 'attributes': {'quality': '양품'}}],
                    'categories': [{'id': 101, 'name': '스크래치'}]}
            (root / 'labels' / 'sample.json').write_text(json.dumps(data), encoding='utf-8-sig')
            items, summary = inspector.build_catalog(root)
            self.assertEqual(summary['indexed_images'], 1)
            self.assertEqual(items[0]['quality'], '불량품')
            self.assertEqual(items[0]['annotation_count'], 1)
            self.assertEqual(items[0]['orientation'], 6)
            self.assertEqual(items[0]['width'], 20)
            # A duplicate basename must not be silently matched.
            (root / 'images' / 'duplicate').mkdir()
            Image.new('RGB', (20, 10)).save(root / 'images' / 'duplicate' / 'sample.JPG')
            items, summary = inspector.build_catalog(root)
            self.assertEqual(len(items), 0)
            self.assertEqual(len(summary['failures']), 1)

    def test_http_preview_crop_and_review_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'images').mkdir()
            (root / 'labels').mkdir()
            exif = Image.Exif()
            exif[274] = 3
            image_path = root / 'images' / 'sample.jpg'
            sample = Image.new('RGB', (20, 10), 'white')
            sample.paste((0, 0, 0), (0, 0, 10, 10))
            sample.save(image_path, exif=exif)
            original_bytes = image_path.read_bytes()
            data = {'images': [{'id': 1, 'file_name': 'sample.jpg', 'width': 20, 'height': 10}],
                    'annotations': [{'image_id': 1, 'category_id': 101, 'attributes': {'quality': '不良'},
                                     'segmentation': [[1, 1, 8, 1, 8, 8, 1, 8]]}],
                    'categories': [{'id': 101, 'name': 'scratch'}]}
            (root / 'labels' / 'sample.json').write_text(json.dumps(data), encoding='utf-8-sig')
            process = subprocess.Popen([sys.executable, inspector.__file__, '--data-root', str(root),
                                        '--output', str(root / 'out'), '--no-browser'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', env=__import__('os').environ | {'PYTHONIOENCODING': 'utf-8'})
            try:
                address = None
                for _ in range(100):
                    line = process.stdout.readline()
                    if not line:
                        break
                    if line.startswith('점검 화면: '):
                        address = line.strip().split('점검 화면: ')[1]
                        break
                self.assertIsNotNone(address)
                def request(path, payload=None, token=None):
                    headers = {'Content-Type': 'application/json'}
                    if token:
                        headers['X-Inspection-Token'] = token
                    body = None if payload is None else json.dumps(payload).encode()
                    with urlopen(Request(address + path, body, headers), timeout=10) as response:
                        return response.read()
                catalog = json.loads(request('/api/catalog'))
                preview = Image.open(io.BytesIO(request('/api/image?id=0')))
                self.assertEqual(preview.size, (20, 10))
                self.assertNotIn(274, preview.getexif())
                rotated = Image.open(io.BytesIO(request('/api/image?id=0&mode=exif')))
                self.assertLess(preview.getpixel((1, 1))[0], 50)
                self.assertGreater(rotated.getpixel((1, 1))[0], 200)
                self.assertNotIn(274, rotated.getexif())
                patch = Image.open(io.BytesIO(request('/api/patch?id=0&grid=2&patch=0')))
                self.assertEqual(patch.size, (10, 5))
                evidence = json.loads(request('/api/evidence?id=0&grid=2&patch=0'))
                self.assertGreater(evidence['mask_pixels'], 0)
                payload = {'id': 0, 'grid': 2, 'patch': 0, 'observation': 'unclear', 'note': 'unit test'}
                with self.assertRaises(HTTPError) as caught:
                    request('/api/review', payload)
                self.assertEqual(caught.exception.code, 403)
                saved = json.loads(request('/api/review', payload, catalog['token']))
                record = json.loads(Path(saved['path']).read_text(encoding='utf-8'))
                self.assertEqual(record['box_xyxy'], [0, 0, 10, 5])
                self.assertEqual(record['purpose'], 'inspection_only_not_training_label')
                payload['mode'] = 'exif'
                request('/api/review', payload, catalog['token'])
                records = [json.loads(line) for line in Path(saved['path']).read_text(encoding='utf-8').splitlines()]
                self.assertEqual(records[-1]['coordinate_frame'], 'exif_transposed_pixels_json_unchanged')
                self.assertEqual(records[0]['coordinate_frame'], 'stored_pixels_no_exif_transpose')
                self.assertEqual(image_path.read_bytes(), original_bytes)
            finally:
                process.terminate()
                process.communicate(timeout=10)

    def test_rotated_dimensions_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rotated.jpg'
            exif = Image.Exif()
            exif[274] = 6
            Image.new('RGB', (20, 10)).save(path, exif=exif)
            item = {'image_path': str(path), 'width': 10, 'height': 20}
            inspector.validate_frame(item, 'exif')
            with self.assertRaises(ValueError):
                inspector.validate_frame(item, 'stored')


if __name__ == '__main__':
    unittest.main()
