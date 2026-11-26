"""28×28 LayerCAM for the isolated FRAME trial API."""

from PIL import Image, ImageOps


def cam(engine, path, layer, dest, target="defect", *, render_overlay=False):
    if target != "defect" or render_overlay:
        raise ValueError("FRAME LayerCAM expects the DEFECT logit and shared JET rendering")
    torch, np = engine.torch, engine.np
    cache = {}
    handle = engine.model.get_submodule(layer).register_forward_hook(
        lambda _module, _inputs, output: cache.update(activation=output)
    )
    try:
        with torch.enable_grad():
            tensor = engine.tensor(path).unsqueeze(0).cuda().requires_grad_(True)
            logits = engine.model(tensor)
            activation = cache["activation"]
            if tuple(activation.shape[:3]) != (1, 28, 28) or not torch.isfinite(logits).all():
                raise ValueError("Unexpected FRAME LayerCAM output shape or logits")
            gradient, = torch.autograd.grad(logits[0, 1], activation)
            if not torch.isfinite(activation).all() or not torch.isfinite(gradient).all():
                raise ValueError("Nonfinite FRAME LayerCAM activation or gradient")
            # Same positive-gradient weighted sum as the held-out comparison.
            a = activation.permute(0, 3, 1, 2)
            g = gradient.permute(0, 3, 1, 2)
            raw = (g.relu()*a).sum(1).relu()[0].detach().cpu().numpy()
    finally:
        handle.remove()
    if not np.isfinite(raw).all():
        raise ValueError("Nonfinite LayerCAM")
    np.save(dest / "raw.npy", raw)
    lo, hi = float(raw.min()), float(raw.max())
    if hi-lo <= max(1e-12, abs(hi)*1e-6):
        status = "ZERO_MAP" if lo == hi == 0 else "CONSTANT_MAP"
        return dict(status=status, rawMin=lo, rawMax=hi), None, None
    full = np.asarray(Image.fromarray(((raw-lo)/(hi-lo)).astype("float32")).resize(
        (224, 224), Image.Resampling.BILINEAR
    ))
    with Image.open(path) as source:
        original = ImageOps.exif_transpose(source)
        contained = ImageOps.contain(original, (224, 224), method=Image.Resampling.BICUBIC)
    w, h = contained.size
    left, top = round((224-w)/2), round((224-h)/2)
    return dict(status="GENERATED", rawMin=lo, rawMax=hi,
                paddingCrop=[left, top, left+w, top+h]), full, None
