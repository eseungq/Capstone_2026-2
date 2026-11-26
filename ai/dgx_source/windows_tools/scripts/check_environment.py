"""AI 개발 환경과 GPU 추론 가능 여부를 확인한다."""

from __future__ import annotations

import platform

import cv2
import pandas
import sklearn
import timm
import torch
import yaml


def main() -> None:
    print(f"Python: {platform.python_version()}")
    print(f"PyTorch: {torch.__version__}")
    print(f"PyTorch CUDA runtime: {torch.version.cuda}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"OpenCV: {cv2.__version__}")
    print(f"timm: {timm.__version__}")
    print(f"pandas: {pandas.__version__}")
    print(f"scikit-learn: {sklearn.__version__}")
    print(f"PyYAML: {yaml.__version__}")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU를 사용할 수 없습니다.")

    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    print(f"GPU: {properties.name}")
    print(f"VRAM: {properties.total_memory / 1024**3:.2f} GB")

    model = timm.create_model(
        "swin_tiny_patch4_window7_224",
        pretrained=False,
        num_classes=2,
    ).to(device)
    model.eval()

    sample = torch.randn(1, 3, 224, 224, device=device)
    with torch.inference_mode():
        output = model(sample)

    print(f"Swin output shape: {tuple(output.shape)}")
    print("Environment check: PASS")


if __name__ == "__main__":
    main()
