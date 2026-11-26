"""DGX Swin-Tiny image-level door quality training. No test image evaluation."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import random
import shutil
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

CONFIG = dict(model_name='swin_tiny_patch4_window7_224.ms_in1k', pretrained=True, image_size=224,
              batch_size=8, epochs=20, learning_rate=1e-4, weight_decay=1e-4,
              seed=42, num_workers=0, amp=False, augmentation='none',
              selection='internal_validation_f1', prediction_cutoff=0.5,
              resize='aspect-ratio preserved, whole image padded to square',
              orientation='Pillow ImageOps.exif_transpose', automatic_pass=False)
EXPECTED = {'train': {0: 5149, 1: 6405},
            'internal_validation': {0: 909, 1: 1130},
            'test': {0: 757, 1: 943}}
FILES = {'train': 'door_train.csv', 'internal_validation': 'door_internal_validation.csv',
         'test': 'door_test.csv'}


def audit(root):
    tables, report, names = {}, {}, {}
    for split, filename in FILES.items():
        path = root / 'outputs/manifests' / filename
        if not path.is_file():
            raise FileNotFoundError(f'분할 파일이 없습니다: {path}')
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if not {'image_path', 'quality', 'class_id'}.issubset(reader.fieldnames or []):
                raise ValueError(f'{path.name}: image_path, quality, class_id 열이 필요합니다.')
            rows = list(reader)
        counts, keys = Counter(), []
        for row in rows:
            label = int(row['class_id'])
            if {'양품': 0, '불량품': 1}.get(row['quality']) != label:
                raise ValueError(f'정상·불량 번호가 일치하지 않습니다: {row}')
            image = Path(row['image_path']).expanduser()
            if not image.is_absolute():
                image = root / image
            if not image.is_file():
                raise FileNotFoundError(f'이미지 경로를 확인하세요: {image}')
            row['image_path'] = str(image.resolve())
            row['class_id'] = label
            keys.append(image.name.casefold())
            counts[label] += 1
        if dict(counts) != EXPECTED[split]:
            raise ValueError(f'{split} 분포가 기존 분할과 다릅니다: {dict(counts)} / 예상 {EXPECTED[split]}')
        if len(keys) != len(set(keys)):
            raise ValueError(f'{split}: 중복 파일명이 있습니다.')
        tables[split], names[split] = rows, set(keys)
        report[split] = dict(path=str(path), rows=len(rows), class_counts=dict(counts),
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    for a, b in [('train', 'internal_validation'), ('train', 'test'), ('internal_validation', 'test')]:
        overlap = names[a] & names[b]
        if overlap:
            raise ValueError(f'{a}/{b} 중복 파일명: {len(overlap)}개')
    # Filename checks do not establish absence of visual duplicates or same physical parts.
    return tables, report


def metrics(labels, predictions):
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, predictions))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, predictions))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, predictions))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, predictions))
    ratio = lambda a, b: a / b if b else None
    return dict(accuracy=ratio(tp + tn, len(labels)), precision=ratio(tp, tp + fp),
                recall=ratio(tp, tp + fn), f1=ratio(2 * tp, 2 * tp + fp + fn),
                missed_defect_rate=ratio(fn, tp + fn), tp=tp, tn=tn, fp=fp, fn=fn)


def write_csv(path, rows, fieldnames=None):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.home() / 'car-parts-ai')
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    tables, audit_report = audit(root)
    print('분할 점검 완료:', {s: len(r) for s, r in tables.items()})
    print('파일명 기준 중복 없음. 이미지 내용·동일 부품 중복까지 보장하는 검사는 아닙니다.')
    if args.audit_only:
        print(json.dumps(audit_report, ensure_ascii=False, indent=2))
        return

    import numpy as np
    import torch
    import timm
    from PIL import Image, ImageOps
    from torch.utils.data import DataLoader, Dataset
    from torchvision.transforms import functional as TF
    from timm.data import resolve_model_data_config

    if not torch.cuda.is_available():
        raise RuntimeError('GPU가 없습니다. DGX의 기존 PyTorch 커널에서 실행하세요.')
    random.seed(CONFIG['seed'])
    np.random.seed(CONFIG['seed'])
    torch.manual_seed(CONFIG['seed'])
    torch.cuda.manual_seed_all(CONFIG['seed'])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    # Repeated runs can still differ across hardware/library versions.
    generator = torch.Generator().manual_seed(CONFIG['seed'])
    device = torch.device('cuda')
    print('GPU:', torch.cuda.get_device_name(0))
    print('첫 실행은 사전학습 가중치 다운로드를 위해 인터넷 연결이 필요합니다.')
    model = timm.create_model(CONFIG['model_name'], pretrained=CONFIG['pretrained'], num_classes=2).to(device)
    data_config = resolve_model_data_config(model)
    if tuple(data_config['input_size']) != (3, CONFIG['image_size'], CONFIG['image_size']):
        raise ValueError('사전학습 모델의 기본 입력 크기와 설정이 다릅니다. 임의 변환하지 않습니다.')
    estimated_bytes = sum(p.numel() for p in model.parameters()) * 12 * (CONFIG['epochs'] + 1) + 2 * 1024**3
    free_bytes = shutil.disk_usage(root).free
    print(f'저장 여유 공간: {free_bytes / 1024**3:.1f} GB / 예상 필요: {estimated_bytes / 1024**3:.1f} GB')
    if free_bytes < estimated_bytes:
        raise RuntimeError('회차별 체크포인트 저장 공간이 부족합니다. 데이터나 기존 모델을 지우지 말고 저장 위치를 확인하세요.')
    mean, std = data_config['mean'], data_config['std']
    fill = tuple(round(x * 255) for x in mean)

    class DoorDataset(Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = self.rows[index]
            try:
                with Image.open(row['image_path']) as source:
                    image = ImageOps.exif_transpose(source).convert('RGB')
                image = ImageOps.pad(image, (CONFIG['image_size'], CONFIG['image_size']),
                                     method=Image.Resampling.BICUBIC, color=fill)
                tensor = TF.normalize(TF.to_tensor(image), mean, std)
                return tensor, row['class_id'], index
            except Exception as e:
                raise RuntimeError(f"이미지 읽기 실패: {row['image_path']} / {e}") from e

    train_loader = DataLoader(DoorDataset(tables['train']), batch_size=CONFIG['batch_size'],
                              shuffle=True, generator=generator, num_workers=CONFIG['num_workers'], pin_memory=True)
    val_loader = DataLoader(DoorDataset(tables['internal_validation']), batch_size=CONFIG['batch_size'],
                            shuffle=False, num_workers=CONFIG['num_workers'], pin_memory=True)
    images, labels, _ = next(iter(val_loader))
    if images.shape[1:] != (3, CONFIG['image_size'], CONFIG['image_size']) or not torch.isfinite(images).all():
        raise ValueError('첫 배치 크기 또는 유한값 검사 실패')
    print('첫 배치:', tuple(images.shape), ' / 라벨:', labels.tolist())
    model.eval()
    with torch.inference_mode():
        probe = model(images.to(device))
    if probe.shape != (len(labels), 2) or not torch.isfinite(probe).all():
        raise ValueError('모델 출력 크기 또는 유한값 검사 실패')
    print('Swin 모델 출력 확인:', tuple(probe.shape))
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG['learning_rate'], weight_decay=CONFIG['weight_decay'])
    # First reference experiment uses FP32; mixed precision is not silently enabled.
    run_dir = root / 'outputs/training' / datetime.now().strftime('door_swin_tiny_%Y%m%d_%H%M%S_%f')
    run_dir.mkdir(parents=True, exist_ok=False)
    versions = {p: importlib.metadata.version(p) for p in ['torch', 'torchvision', 'timm', 'Pillow', 'numpy']}
    metadata = dict(config=CONFIG, normalization=dict(mean=list(mean), std=list(std)),
                    manifests=audit_report, versions=versions, class_mapping={'양품': 0, '불량품': 1},
                    scope='image-level door quality; no localization, calibration or AUTO_PASS',
                    test_images_evaluated=False, gpu=torch.cuda.get_device_name(0),
                    pretrained_configuration=model.pretrained_cfg,
                    cuda_build=torch.version.cuda, cudnn_version=torch.backends.cudnn.version())
    (run_dir / 'run_config.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('저장 폴더:', run_dir, flush=True)
    history, best_f1 = [], -1.0
    for epoch in range(1, CONFIG['epochs'] + 1):
        epoch_start = time.perf_counter()
        model.train()
        total_loss, seen = 0.0, 0
        for step, (images, labels, _) in enumerate(train_loader, 1):
            images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, labels)
            if not torch.isfinite(loss):
                raise RuntimeError(f'손실값이 유한하지 않습니다: epoch={epoch}, step={step}')
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(labels)
            seen += len(labels)
            if step == 1 or step % 100 == 0:
                print(f'학습 {epoch}/{CONFIG["epochs"]} · 배치 {step}/{len(train_loader)} · loss {total_loss / seen:.4f}', flush=True)
        model.eval()
        actual, predicted, outputs = [], [], []
        val_loss = 0.0
        with torch.inference_mode():
            for images, labels, indices in val_loader:
                logits = model(images.to(device, non_blocking=True))
                if not torch.isfinite(logits).all():
                    raise RuntimeError('검증 예측값에 NaN/Inf가 있습니다.')
                val_loss += criterion(logits, labels.to(device)).item() * len(labels)
                scores = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
                for index, y, score in zip(indices.tolist(), labels.tolist(), scores):
                    p = int(score >= CONFIG['prediction_cutoff'])
                    row = tables['internal_validation'][index]
                    actual.append(y)
                    predicted.append(p)
                    outputs.append(dict(image_path=row['image_path'], quality=row['quality'], class_id=y,
                                        predicted_class=p, raw_defect_score=score, correct=int(y == p)))
        result = dict(epoch=epoch, train_loss=total_loss / seen,
                      validation_loss=val_loss / len(actual), elapsed_seconds=time.perf_counter() - epoch_start,
                      **metrics(actual, predicted))
        history.append(result)
        write_csv(run_dir / 'history.csv', history)
        checkpoint = dict(epoch=epoch, model_state_dict=model.state_dict(),
                          optimizer_state_dict=optimizer.state_dict(), metadata=metadata, metrics=result)
        checkpoint.update(python_rng_state=random.getstate(), numpy_rng_state=np.random.get_state(),
                          torch_rng_state=torch.get_rng_state(), cuda_rng_state=torch.cuda.get_rng_state_all(),
                          train_loader_rng_state=generator.get_state())
        torch.save(checkpoint, run_dir / f'epoch_{epoch:02d}.pt')
        f1 = result['f1'] if result['f1'] is not None else -1
        if f1 > best_f1:
            best_f1 = f1
            torch.save(checkpoint, run_dir / 'best.pt')
            write_csv(run_dir / 'best_internal_validation_predictions.csv', outputs)
            errors = [r for r in outputs if not r['correct']]
            write_csv(run_dir / 'best_internal_validation_errors.csv', errors, list(outputs[0]))
            (run_dir / 'best_metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('내부 검증:', json.dumps(result, ensure_ascii=False), flush=True)
    print('학습 완료:', run_dir)
    print('공유할 파일: best_metrics.json / history.csv / run_config.json')
    print('내부 검증은 모델 선택용입니다. 최종 시험 1,700장은 평가하지 않았습니다.')
    print('raw_defect_score는 보정 전 점수입니다. 0.5는 분류 비교 기준이며 passThreshold가 아닙니다.')


if __name__ == '__main__':
    main()
