"""Read-only, single internal-validation image inference; no training or test evaluation."""
import argparse
import ast
import csv
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import sys


SELECTED = ('/path/to/private/validated-project/data/images/Training/도어/스크래치/'
            '204_101_10_00362cff-0849-454d-8b84-6fe875eac34f.jpg')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-code', type=Path, default=Path(
        '/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009/train_door_swin.py'))
    parser.add_argument('--run-dir', type=Path, default=Path(
        '/path/to/private/validated-project/outputs/training/door_swin_tiny_20261008_183758_369671'))
    args = parser.parse_args()
    # Do not create __pycache__ in the original training-code directory.
    sys.dont_write_bytecode = True
    source = args.training_code.read_text(encoding='utf-8')
    tree = ast.parse(source)
    guard = tree.body[-1]
    if not (isinstance(guard, ast.If) and ast.unparse(guard.test) == "__name__ == '__main__'"):
        raise RuntimeError('Unexpected training entry-point guard; refusing import.')
    spec = importlib.util.spec_from_file_location('original_door_training', args.training_code)
    training = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(training)  # __name__ is not __main__; does not call main().
    config = json.loads((args.run_dir / 'run_config.json').read_text(encoding='utf-8'))
    if training.CONFIG != config['config']:
        raise RuntimeError('Training code CONFIG differs from saved run configuration.')
    if config['class_mapping'] != {'양품': 0, '불량품': 1} or config['config']['amp']:
        raise RuntimeError('Unexpected class mapping or mixed precision setting.')
    with (args.run_dir / 'best_internal_validation_predictions.csv').open(
            encoding='utf-8-sig', newline='') as f:
        matches = [r for r in csv.DictReader(f) if r['image_path'] == SELECTED]
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one matching internal-validation CSV row.')
    row = matches[0]

    import numpy as np
    import torch
    import timm
    from PIL import Image, ImageOps
    from torch.utils.data import Dataset
    from torchvision.transforms import functional as TF
    from timm.data import resolve_model_data_config
    versions = {p: version(p)
                for p in ['torch', 'torchvision', 'timm', 'Pillow', 'numpy']}
    print('Runtime versions:', json.dumps(versions), flush=True)
    print('Recorded versions:', json.dumps(config['versions']), flush=True)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU unavailable; use the existing NVIDIA GPU container.')
    training.random.seed(training.CONFIG['seed'])
    np.random.seed(training.CONFIG['seed'])
    torch.manual_seed(training.CONFIG['seed'])
    torch.cuda.manual_seed_all(training.CONFIG['seed'])
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    print('GPU:', torch.cuda.get_device_name(0), flush=True)
    # This is the user's own trusted training checkpoint. It includes numpy RNG
    # objects, so loading the complete checkpoint requires weights_only=False.
    checkpoint = torch.load(args.run_dir / 'best.pt', map_location='cpu', weights_only=False)
    print('Checkpoint keys:', list(checkpoint), flush=True)
    print('Checkpoint epoch:', checkpoint['epoch'], flush=True)
    # JSON turns tuples (e.g. pretrained input_size/mean/std) into lists.
    # Compare both metadata objects in their saved JSON representation.
    if json.loads(json.dumps(checkpoint['metadata'])) != config:
        raise RuntimeError('Checkpoint metadata differs from run_config.json.')
    model = timm.create_model(training.CONFIG['model_name'], pretrained=False, num_classes=2)
    model.load_state_dict(checkpoint['model_state_dict'], strict=True)
    model = model.float().to('cuda').eval()
    data_config = resolve_model_data_config(model)
    mean, std = data_config['mean'], data_config['std']
    if (tuple(data_config['input_size']) != (3, 224, 224)
            or list(mean) != config['normalization']['mean']
            or list(std) != config['normalization']['std']):
        raise RuntimeError('Model preprocessing configuration differs from saved run.')
    fill = tuple(round(x * 255) for x in mean)
    # DoorDataset lives inside main() in the original code. Compile only its
    # unchanged class definition, without executing main() or any training code.
    main_node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    dataset_node = next(n for n in main_node.body if isinstance(n, ast.ClassDef) and n.name == 'DoorDataset')
    namespace = dict(Dataset=Dataset, Image=Image, ImageOps=ImageOps, TF=TF,
                     CONFIG=training.CONFIG, mean=mean, std=std, fill=fill)
    exec(compile(ast.Module(body=[dataset_node], type_ignores=[]),
                 str(args.training_code), 'exec'), namespace)
    sample = dict(row, class_id=int(row['class_id']))
    tensor, label, _ = namespace['DoorDataset']([sample])[0]
    if tensor.shape != (3, 224, 224) or tensor.dtype != torch.float32 or not torch.isfinite(tensor).all():
        raise RuntimeError('Unexpected input tensor.')
    with torch.inference_mode():
        logits = model(tensor.unsqueeze(0).to('cuda'))
        if logits.shape != (1, 2) or not torch.isfinite(logits).all():
            raise RuntimeError('Invalid model output.')
        score = torch.softmax(logits, dim=1)[:, 1][0].item()
    predicted = int(score >= training.CONFIG['prediction_cutoff'])
    names = {0: '양품', 1: '불량품'}
    csv_predicted, csv_score = int(row['predicted_class']), float(row['raw_defect_score'])
    print(json.dumps(dict(image_path=SELECTED, ground_truth=dict(class_id=label, name=names[label]),
                         csv_prediction=dict(class_id=csv_predicted, name=names[csv_predicted]),
                         new_prediction=dict(class_id=predicted, name=names[predicted]),
                         csv_raw_defect_score=csv_score, new_raw_defect_score=score,
                         absolute_score_difference=abs(score - csv_score),
                         predicted_class_matches=(predicted == csv_predicted),
                         exact_score_matches=(score == csv_score),
                         label_follow_up='스크래치 폴더이나 CSV 정답은 양품(0); 후속 확인 필요; 라벨 변경 없음',
                         input_batch_size=1, original_validation_batch_size=config['config']['batch_size']),
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
