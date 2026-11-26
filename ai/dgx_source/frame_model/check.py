"""Read-only preparation checks and optional GPU throughput measurement; never trains."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]

def read_image(row):
    fd = os.open(row['image_archive'], os.O_RDONLY)
    try:
        data = os.pread(fd, int(row['size']), int(row['offset']))
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != row['image_sha256']:
        raise ValueError('Image byte hash mismatch: ' + row['image_id'])
    with Image.open(io.BytesIO(data)) as image:
        display = ImageOps.exif_transpose(image).convert('RGB')
        return display, ImageOps.pad(display, (224, 224), method=Image.Resampling.BICUBIC, color=(124,116,104))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['check','benchmark'], default='check')
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--steps', type=int, default=10)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error('--steps must be positive')
    prep = args.preparation or Path(json.loads((ROOT/'frame_model/latest_preparation.json').read_text())['preparation'])
    config = json.loads((prep/'config.json').read_text())
    rows, groups, images = {}, set(), set()
    for name, stat in config['archive_stats'].items():
        actual = Path(name).stat()
        assert (actual.st_size, actual.st_mtime_ns) == (stat['bytes'], stat['mtime_ns']), name
    for role, manifest in config['manifests'].items():
        data = Path(manifest['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == manifest['sha256'], role
        rows[role] = list(csv.DictReader(io.StringIO(data.decode())))
        current_groups = {r['group_id'] for r in rows[role]}
        current_images = {r['image_sha256'] for r in rows[role]}
        assert not groups & current_groups and not images & current_images, 'Cross-role overlap'
        assert len(current_images) == len(rows[role]) == config['roles'][role]
        groups.update(current_groups); images.update(current_images)
    output = ROOT/'outputs/frame_checks'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output.mkdir(parents=True)
    # Reserved calibration/policy pixels are not opened. One image per type/class in each learning role.
    samples, processed = [], []
    for role in ['train','model_selection']:
        selected = {}
        for row in rows[role]:
            selected.setdefault((row['defect_type'],row['class_id']),row)
        assert len(selected) == 8
        for row in selected.values():
            display, padded = read_image(row)
            name = f'{role}_{len(samples):02d}.png'
            padded.save(output/name)
            samples.append({'role':role,'image_id':row['image_id'],'type':row['defect_type'],'class_id':int(row['class_id']),'display_size':display.size,'input':name})
            processed.append(padded)
    report = {'status':'passed','mode':args.mode,'preparation':str(prep),'roles':config['roles'],'sample_count':len(samples),'samples':samples,'training_started':False,'gpu_verified':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.mode == 'benchmark':
        import importlib.metadata as metadata
        import torch
        import timm
        assert torch.cuda.is_available(), 'CUDA unavailable'
        torch.manual_seed(config['seed'])
        # Random weights measure compute only: no download, no accuracy evaluation, no optimizer.
        model = timm.create_model(config['model_name'],pretrained=False,num_classes=2).cuda().eval()
        batch = torch.stack([torch.frombuffer(bytearray(im.tobytes()),dtype=torch.uint8).reshape(224,224,3).permute(2,0,1).float()/255 for im in processed[:config['batch_size']]]).cuda()
        mean = torch.tensor(config['mean'],device='cuda').view(1,3,1,1)
        std = torch.tensor(config['std'],device='cuda').view(1,3,1,1)
        batch = (batch-mean)/std
        target = torch.zeros(len(batch),dtype=torch.long,device='cuda')
        def step(backward):
            if backward:
                model.zero_grad(set_to_none=True)
                torch.nn.functional.cross_entropy(model(batch),target).backward()
            else:
                with torch.no_grad(): model(batch)
        times = {}
        for backward in [False,True]:
            for _ in range(2): step(backward)
            torch.cuda.synchronize(); start=time.perf_counter()
            for _ in range(args.steps): step(backward)
            torch.cuda.synchronize()
            times['forward_backward_ms' if backward else 'forward_ms']=(time.perf_counter()-start)*1000/args.steps
        report.update(gpu_verified=True,gpu=torch.cuda.get_device_name(0),versions={p:metadata.version(p) for p in ['torch','torchvision','timm','Pillow','numpy']},benchmark=times,benchmark_batch_size=len(batch),benchmark_steps=args.steps,benchmark_scope='Random weights, eval mode, FP32; cached input tensor; backward without optimizer; excludes archive IO, optimizer, validation, checkpoint and startup. Not a training-duration estimate or model evaluation.')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('[FRAME CHECK PASSED]', output/'report.json',flush=True)

if __name__=='__main__': main()
