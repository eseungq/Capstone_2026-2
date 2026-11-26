"""Frozen 10-epoch variant of train.py; data and model settings otherwise preserved."""
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
              batch_size=8, epochs=10, learning_rate=1e-4, weight_decay=1e-4,
              seed=42, num_workers=0, amp=False, augmentation='none',
              selection='model_selection_f1', prediction_cutoff=0.5,
              resize='aspect-ratio preserved, whole image padded to square',
              orientation='Pillow ImageOps.exif_transpose', automatic_pass=False)
def audit(root, config_path=None):
    from door_experiment.preflight import audit_manifests
    return audit_manifests(root, config_path)


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


def smoke_subset(tables):
    """Fixed balanced subsets; original manifests stay unchanged."""
    selected = {}
    for role, per_class in [('train', 32), ('model_selection', 16)]:
        rng = random.Random(42)
        by_class = []
        for label in (0, 1):
            candidates = sorted((r for r in tables[role] if r['class_id'] == label), key=lambda r: r['image_path'])
            if len(candidates) < per_class:
                raise ValueError('Insufficient smoke samples: ' + role)
            by_class.append(rng.sample(candidates, per_class))
        selected[role] = [row for pair in zip(*by_class) for row in pair]
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--mode', choices=['check', 'gpu-check', 'smoke', 'train'], default='check')
    parser.add_argument('--start-training', action='store_true')
    parser.add_argument('--experiment-config', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/door_visible_region_experiment_v3_10epochs.json')
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.mode == 'train' and not args.start_training:
        parser.error('train requires --start-training; preparation does not authorize training')
    if args.start_training and args.mode != 'train':
        parser.error('--start-training is only valid with train')
    tables, audit_report = audit(root, args.experiment_config)
    frozen_config = audit_report['provenance']['config']
    if frozen_config.get('training_config'):
        if json.loads((root / frozen_config['training_config']).read_text()) != CONFIG:
            raise ValueError('Hyperparameters differ from frozen experiment')
    print('분할 점검 완료:', {s: len(r) for s, r in tables.items()})
    print('알려진 그룹·이미지 경계 검사 통과. 미확인 유사 사진·동일 실물의 독립성은 보장하지 않습니다.')
    if args.mode == 'check':
        print(json.dumps(audit_report, ensure_ascii=False, indent=2))
        return

    effective_config = dict(CONFIG)
    if args.mode == 'smoke':
        tables = smoke_subset(tables)
        effective_config['epochs'] = 1
        print('[DOOR SMOKE] train=64 (GOOD32/DEFECT32), model_selection=32 (GOOD16/DEFECT16); execution test only')

    import numpy as np
    import torch
    import timm
    from PIL import Image, ImageOps
    from torch.utils.data import DataLoader, Dataset
    from torchvision.transforms import functional as TF
    from timm.data import resolve_model_data_config

    expected_versions = {'torch':'2.10.0a0+b558c986e8.nv25.11', 'torchvision':'0.25.0a0+7a13ad0f', 'timm':'1.0.30', 'Pillow':'12.0.0', 'numpy':'2.1.0'}
    for package, expected in expected_versions.items():
        if importlib.metadata.version(package) != expected:
            raise RuntimeError('Recorded environment mismatch: ' + package)
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
    if args.mode in ('train', 'smoke') and free_bytes < estimated_bytes:
        raise RuntimeError('회차별 체크포인트 저장 공간이 부족합니다. 데이터나 기존 모델을 지우지 말고 저장 위치를 확인하세요.')
    mean, std = data_config['mean'], data_config['std']
    if tuple(mean) != (0.485, 0.456, 0.406) or tuple(std) != (0.229, 0.224, 0.225):
        raise ValueError('Normalization differs from original training')
    fill = tuple(round(x * 255) for x in mean)
    if fill != (124, 116, 104):
        raise ValueError('Padding differs from original training')

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
    val_loader = DataLoader(DoorDataset(tables['model_selection']), batch_size=CONFIG['batch_size'],
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
    if args.mode == 'gpu-check':
        torch.cuda.synchronize()
        print('[DOOR GPU CHECK PASSED] no optimizer or training updates; visible-region scope')
        return
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG['learning_rate'], weight_decay=CONFIG['weight_decay'])
    # First reference experiment uses FP32; mixed precision is not silently enabled.
    run_dir = root / 'outputs/door_next_training' / datetime.now().strftime(('smoke_' if args.mode == 'smoke' else 'door_visible_') + '%Y%m%d_%H%M%S_%f')
    run_dir.mkdir(parents=True, exist_ok=False)
    versions = {p: importlib.metadata.version(p) for p in ['torch', 'torchvision', 'timm', 'Pillow', 'numpy']}
    metadata = dict(config=effective_config, mode=args.mode, performance_claim_allowed=False, normalization=dict(mean=list(mean), std=list(std)),
                    manifests=audit_report, versions=versions, class_mapping={'양품': 0, '불량품': 1},
                    scope='visible target DOOR region only; no localization, calibration or AUTO_PASS',
                    test_images_evaluated=False, gpu=torch.cuda.get_device_name(0),
                    pretrained_configuration=model.pretrained_cfg,
                    cuda_build=torch.version.cuda, cudnn_version=torch.backends.cudnn.version())
    shutil.copy2(Path(__file__), run_dir / 'training_source.py')
    metadata['training_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (run_dir / 'run_config.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    for role, rows in tables.items():
        write_csv(run_dir / (role + '_used.csv'), rows)
    (run_dir / 'status.json').write_text(json.dumps(dict(status='running', mode=args.mode)))
    initial_parameter = next(model.parameters()).detach().clone() if args.mode == 'smoke' else None
    print('저장 폴더:', run_dir, flush=True)
    history, best_f1 = [], -1.0
    for epoch in range(1, effective_config['epochs'] + 1):
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
            if args.mode == 'smoke':
                grads = [p.grad for p in model.parameters() if p.grad is not None]
                if not grads or any(not torch.isfinite(g).all() for g in grads):
                    raise RuntimeError('Smoke gradients missing or nonfinite')
            optimizer.step()
            total_loss += loss.item() * len(labels)
            seen += len(labels)
            if step == 1 or step % 100 == 0:
                print(f'학습 {epoch}/{effective_config["epochs"]} · 배치 {step}/{len(train_loader)} · loss {total_loss / seen:.4f}', flush=True)
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
                    row = tables['model_selection'][index]
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
            write_csv(run_dir / 'best_model_selection_predictions.csv', outputs)
            errors = [r for r in outputs if not r['correct']]
            write_csv(run_dir / 'best_model_selection_errors.csv', errors, list(outputs[0]))
            (run_dir / 'best_metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('내부 검증:', json.dumps(result, ensure_ascii=False), flush=True)
    completion = dict(status='completed', mode=args.mode, final_test_read=False, calibration_fitted=False)
    if args.mode == 'smoke':
        changed = not torch.equal(initial_parameter, next(model.parameters()).detach())
        if not changed:
            raise RuntimeError('Smoke parameter update not observed')
        # Only reload the checkpoint produced by this run, never an external file.
        saved = torch.load(run_dir / 'best.pt', map_location=device, weights_only=False)
        if saved['epoch'] != 1 or saved['metadata']['mode'] != 'smoke':
            raise RuntimeError('Unexpected smoke checkpoint metadata')
        for key, value in model.state_dict().items():
            if not torch.equal(value, saved['model_state_dict'][key]):
                raise RuntimeError('Saved state differs: ' + key)
        model.load_state_dict(saved['model_state_dict'], strict=True)
        optimizer.load_state_dict(saved['optimizer_state_dict'])
        model.eval()
        with torch.inference_mode():
            reloaded_logits = model(images.to(device))
        if not torch.isfinite(reloaded_logits).all():
            raise RuntimeError('Reloaded model output is nonfinite')
        completion.update(status='smoke_passed', parameter_update_observed=True,
                          checkpoint_state_exact=True, strict_reload=True,
                          optimizer_reload=True, performance_evaluation=False)
    (run_dir / 'status.json').write_text(json.dumps(completion, indent=2))
    if args.mode == 'smoke':
        print('[DOOR SMOKE PASSED]', run_dir, flush=True)
    if args.mode == 'train':
        print('[DOOR TRAINING COMPLETE]', run_dir, flush=True)
    print('학습 완료:', run_dir)
    print('공유할 파일: best_metrics.json / history.csv / run_config.json')
    print('내부 검증은 모델 선택용입니다. 최종 시험 1,700장은 평가하지 않았습니다.')
    print('raw_defect_score는 보정 전 점수입니다. 0.5는 분류 비교 기준이며 passThreshold가 아닙니다.')


if __name__ == '__main__':
    main()
