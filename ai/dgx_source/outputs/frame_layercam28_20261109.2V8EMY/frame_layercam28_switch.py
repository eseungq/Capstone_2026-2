"""Stage, preflight, and safely switch the two FRAME-only trial listeners."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


PROJECT = Path("/path/to/private/validated-project")
OUT = PROJECT / "outputs"
OLD = {
    8773: OUT / "frame_test_api_jet_20261108.0mqEHz/frame_unified_test_api_20261107.py",
    8774: OUT / "frame_policy_trial_20261109.Pvhh3k/frame_policy_trial_20261109.py",
}
HOST = "127.0.0.1"
ORIGIN = "http://127.0.0.1:8080"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Unexpected source around {old[:70]!r}")
    return source.replace(old, new)


def prepare(stage):
    base, policy = (stage / str(port) for port in (8773, 8774))
    for folder in (base, policy):
        folder.mkdir()
        (folder / "frame_layercam28.py").write_bytes((stage / "frame_layercam28.py").read_bytes())
    server = OLD[8773].read_text()
    for old, new in (
        ('CAM_LAYER = "layers.2.blocks.5.norm1"', 'CAM_LAYER = "layers.1.blocks.1.norm1"'),
        ("from ai_api.diagnostics import cam", "from frame_layercam28 import cam"),
        ('gradcam_layer=CAM_LAYER, gradcam_palette="JET"', 'gradcam_layer=CAM_LAYER, gradcam_method="LayerCAM", gradcam_grid=[28,28], gradcam_palette="JET"'),
        ('        server_version = "FrameAI/development"', '''        server_version = "FrameAI/development"

        def send(self, status, body, **kwargs):
            kwargs["headers"] = {**(kwargs.get("headers") or {}), "X-Frame-CAM-Method": "LayerCAM",
                                 "X-Frame-CAM-Grid": "28x28"}
            return super().send(status, body, **kwargs)'''),
    ):
        server = replace(server, old, new)
    server = replace(server, '    args = parser.parse_args()', '    parser.add_argument("--smoke-only", action="store_true")\n    args = parser.parse_args()')
    server = replace(server, '    server = new_server((args.host, args.port)', '    if args.smoke_only:\n        return\n    server = new_server((args.host, args.port)')
    base_script = base / OLD[8773].name
    compile(server, str(base_script), "exec")
    base_script.write_text(server)
    calibrated = OLD[8774].read_text()
    calibrated = replace(calibrated, 'SOURCE_SERVER = "outputs/frame_test_api_jet_20261108.0mqEHz/frame_unified_test_api_20261107.py"',
                         f"SOURCE_SERVER = {str(base_script.relative_to(PROJECT))!r}")
    if calibrated.count('layers.2.blocks.5.norm1') != 2:
        raise ValueError("Unexpected calibrated wrapper layer references")
    calibrated = calibrated.replace('layers.2.blocks.5.norm1', 'layers.1.blocks.1.norm1')
    calibrated = replace(calibrated, "import argparse", "import argparse\nimport base64\nimport io\nfrom PIL import Image, ImageOps")
    calibrated = replace(calibrated, '                active = gate(', '''                cam = response["gradcam"]
                if photo["expected"] == "GOOD":
                    if cam is not None:
                        raise ValueError("GOOD response must omit CAM")
                else:
                    if not cam or (cam["status"], cam["format"], cam["targetClass"]) != ("GENERATED", "jpeg", "DEFECT"):
                        raise ValueError("Expected a DEFECT LayerCAM JPEG")
                    decoded = base64.b64decode(cam["imageBase64"], validate=True)
                    with Image.open(io.BytesIO(photo["data"])) as img, Image.open(io.BytesIO(decoded)) as overlay:
                        if overlay.format != "JPEG" or overlay.size != ImageOps.exif_transpose(img).size:
                            raise ValueError("LayerCAM image dimensions or type differ")
                        overlay.verify()
                active = gate(''')
    calibrated = replace(calibrated, '                                    testWrongCalibrator=mismatch)',
                         '                                    testWrongCalibrator=mismatch, camStatus=cam["status"] if cam else None)')
    calibrated = replace(calibrated, 'passThreshold=candidate["passThreshold"], policyScope=', 'passThreshold=candidate["passThreshold"], camLayer=api.CAM_LAYER, camMethod="LayerCAM", camGrid=[28,28], policyScope=')
    calibrated = replace(calibrated, 'def main(project, runtime, host, port, origin):', 'def main(project, runtime, host, port, origin, smoke_only=False):')
    calibrated = replace(calibrated, '    server = api.new_server((host, port)', '    if smoke_only:\n        return\n    server = api.new_server((host, port)')
    calibrated = replace(calibrated, '    args = parser.parse_args()', '    parser.add_argument("--smoke-only", action="store_true")\n    args = parser.parse_args()')
    calibrated = replace(calibrated, 'main(args.project, args.runtime, args.host, args.port, args.origin)', 'main(args.project, args.runtime, args.host, args.port, args.origin, args.smoke_only)')
    policy_script = policy / OLD[8774].name
    compile(calibrated, str(policy_script), "exec")
    policy_script.write_text(calibrated)


def command(script, runtime, port):
    tail = ["--host", HOST, "--port", str(port)]
    if port == 8773:
        return [sys.executable, "-u", str(script), "--project", str(PROJECT), "--runtime", str(runtime),
                *tail, "--image-origin", ORIGIN]
    return [sys.executable, "-u", str(script), str(PROJECT), str(runtime), *tail, "--origin", ORIGIN]


def inventory(port):
    with urlopen(f"http://{HOST}:{port}/internal/v1/models", timeout=3) as response:
        return dict(body=json.load(response), method=response.headers.get("X-Frame-CAM-Method"),
                    grid=response.headers.get("X-Frame-CAM-Grid"))


def old_process(port):
    for entry in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = [os.fsdecode(arg) for arg in entry.read_bytes().split(b"\0") if arg]
        except OSError:
            continue
        if args[:3] == [sys.executable, "-u", str(OLD[port])] and "--port" in args and args[args.index("--port")+1] == str(port):
            return int(entry.parent.name), args
    raise ValueError(f"Expected existing listener was not found: {port}")


def start(args, log):
    with log.open("ab") as stream:
        return subprocess.Popen(args, cwd=PROJECT, env=ENV, stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)


def wait_closed(port):
    for _ in range(50):
        with socket.socket() as probe:
            probe.settimeout(.4)
            if probe.connect_ex((HOST, port)):
                return
        time.sleep(.2)
    raise RuntimeError(f"FRAME listener {port} did not release its port")


def wait_ready(process, port, expected, new):
    for _ in range(100):
        if process.poll() is not None:
            break
        try:
            current = inventory(port)
            if current["body"] == expected and (not new or (
                current["method"], current["grid"]
            ) == ("LayerCAM", "28x28")):
                return current
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    return None


def preflight(stage):
    prepare(stage)
    for port in OLD:
        runtime = stage / str(port)
        subprocess.run(command(runtime / OLD[port].name, runtime, port) + ["--smoke-only"],
                       cwd=PROJECT, env=ENV, check=True)
        smoke = json.loads((runtime / "smoke.json").read_text())
        if port == 8773 and (smoke["metadata"]["gradcam_method"], smoke["metadata"]["gradcam_grid"]) != ("LayerCAM", [28,28]):
            raise ValueError("General smoke test did not use LayerCAM")
        if port == 8774 and (smoke["camMethod"], smoke["camGrid"]) != ("LayerCAM", [28,28]):
            raise ValueError("Calibrated smoke test did not use LayerCAM")
        print(f"FRAME {port} preflight passed", flush=True)
    demo_script = OUT / "frame_demo_pack_20261107.st31r1/package.py"
    demo = replace(demo_script.read_text(), str(OUT / "frame_test_api_20261107.d37a92"), str(stage / "8773"))
    demo = replace(demo, "camLayer=CAM_LAYER,", 'camLayer=CAM_LAYER, camMethod="LayerCAM", camGrid=[28,28], camPalette="JET", camAlpha=0.5,')
    demo_path = stage / "demo.py"
    demo_path.write_text(demo)
    subprocess.run([sys.executable, str(demo_path), str(PROJECT), str(stage / "demo")],
                   cwd=PROJECT, env=ENV, check=True)


def cutover(stage):
    for port in OLD:
        if not (stage / str(port) / "smoke.json").is_file():
            raise ValueError(f"Missing preflight evidence: {port}")
    door = inventory(8771)
    before = {port: inventory(port)["body"] for port in OLD}
    processes = {port: old_process(port) for port in OLD}
    switched = {}
    stopped = set()
    try:
        for port in OLD:
            runtime = stage / str(port)
            pid, _ = processes[port]
            os.kill(pid, signal.SIGTERM)
            stopped.add(port)
            wait_closed(port)
            new = start(command(runtime / OLD[port].name, runtime, port), runtime / "server.log")
            switched[port] = new
            if not wait_ready(new, port, before[port], True):
                raise RuntimeError(f"New FRAME listener {port} did not pass readiness")
        after = {port: inventory(port) for port in OLD}
        if inventory(8771) != door:
            raise RuntimeError("DOOR inventory changed during switch")
    except BaseException:
        for port in stopped:
            if port in switched and switched[port].poll() is None:
                switched[port].terminate()
                switched[port].wait(timeout=15)
            wait_closed(port)
            old = start(processes[port][1], OLD[port].parent / "layercam_rollback.log")
            print(f"Restored {port}: {bool(wait_ready(old, port, before[port], False))}", flush=True)
        raise
    result = dict(frame=after, door=door, pids={port: proc.pid for port, proc in switched.items()})
    (stage / "deployment.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "cutover"))
    parser.add_argument("stage", type=Path)
    args = parser.parse_args()
    (preflight if args.mode == "preflight" else cutover)(args.stage)
