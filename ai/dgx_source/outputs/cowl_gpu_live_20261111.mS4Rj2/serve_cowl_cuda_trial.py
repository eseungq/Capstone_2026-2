"""Start the existing calibrated cowl API using the verified CUDA engine."""

from cowl_gpu_trial_compare import CudaEngine
import cowl_unified_calibrated_trial as trial
import torch


if __name__ == "__main__":
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required by this deployment")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    trial.CalibratedEngine = CudaEngine
    print(f"COWL_DEVICE=cuda GPU={torch.cuda.get_device_name()}", flush=True)
    trial.main()
