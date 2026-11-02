#!/usr/bin/env python3
"""동시 접수 처리 시간 측정 (TBD-01). Python 표준 라이브러리만 사용

N건을 연속 접수한 뒤 접수→완료 시간(서버의 receivedAt·completedAt 기준)과 전체 처리 시간을 출력한다.
대기열 길이는 외부 API가 없어 측정 중 DB의 RECEIVED 건수를 docker exec로 주기적으로 조회해 최대값으로 대신한다.
Mock AI 지연은 MOCK_DELAY_MS로 정하고, 실제 AI 연결 후에도 같은 스크립트로 잰다 (--scenario 없이).

  scripts/measure-intake.py --counts 1,5,20 --scenario GOOD_CALIBRATED --mysql-container inspection-mysql
"""
import argparse
import base64
import json
import math
import re
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path


def request(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(api, login_id, password):
    body = json.dumps({"loginId": login_id, "password": password}).encode()
    status, raw = request("POST", f"{api}/auth/login", body, {"Content-Type": "application/json"})
    if status != 200:
        raise SystemExit(f"로그인 실패 {login_id}: HTTP {status} {raw[:200]!r}")
    return json.loads(raw)["data"]["accessToken"]


def submit(api, token, image):
    boundary = uuid.uuid4().hex
    body = b"".join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="partCode"\r\n\r\nDOOR\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="t.png"\r\n'
        "Content-Type: image/png\r\n\r\n".encode(),
        image, f"\r\n--{boundary}--\r\n".encode()])
    status, raw = request("POST", f"{api}/inspections", body, {
        "Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    if status != 202:
        raise SystemExit(f"접수 실패: HTTP {status} {raw[:300]!r}")
    return json.loads(raw)["data"]["inspectionId"]


class QueueSampler(threading.Thread):
    """측정 중 RECEIVED 건수의 최대값. 컨테이너를 지정하지 않으면 측정하지 않음"""

    def __init__(self, container):
        super().__init__(daemon=True)
        self.container, self.max, self.stop_flag = container, None, threading.Event()

    def run(self):
        while self.container and not self.stop_flag.is_set():
            result = subprocess.run(
                ["docker", "exec", self.container, "mysql", "-uinspection", "-pinspection", "inspection", "-N", "-e",
                 "select count(*) from inspection where status = 'RECEIVED'"],
                capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip().isdigit():
                self.max = max(self.max or 0, int(result.stdout.strip()))
            self.stop_flag.wait(0.1)


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1)]


def measure(api, device, worker, image, count, container, wait_seconds):
    sampler = QueueSampler(container)
    sampler.start()
    started = time.monotonic()
    ids = [submit(api, device, image) for _ in range(count)]
    submit_seconds = time.monotonic() - started

    details, pending = {}, set(ids)
    deadline = time.monotonic() + wait_seconds
    while pending and time.monotonic() < deadline:
        for inspection_id in list(pending):
            status, raw = request("GET", f"{api}/inspections/{inspection_id}", None,
                                  {"Authorization": f"Bearer {worker}"})
            data = json.loads(raw).get("data", {}) if status == 200 else {}
            if data.get("status") in ("COMPLETED", "FAILED"):
                details[inspection_id] = data
                pending.discard(inspection_id)
        if pending:
            time.sleep(0.05)
    total_seconds = time.monotonic() - started
    sampler.stop_flag.set()
    sampler.join(timeout=5)
    if pending:
        raise SystemExit(f"{wait_seconds}초 안에 끝나지 않음: {len(pending)}건")

    latencies = [(datetime.fromisoformat(d["completedAt"]) - datetime.fromisoformat(d["receivedAt"])).total_seconds()
                 for d in details.values()]
    inference = [d["ai"]["inferenceTimeMs"] for d in details.values() if d.get("ai", {}).get("inferenceTimeMs") is not None]
    return {
        "count": count,
        "failed": sum(1 for d in details.values() if d["status"] == "FAILED"),
        "submit": submit_seconds,
        "total": total_seconds,
        "avg": statistics.mean(latencies),
        "p95": percentile(latencies, 95),
        "max": max(latencies),
        "inference": statistics.mean(inference) if inference else None,
        "queue": sampler.max,
    }


def table(rows):
    lines = ["| 건수 | FAILED | 접수 전송(초) | 전체 처리(초) | 접수→완료 평균(초) | p95(초) | 최대(초) | inferenceTimeMs 평균 | RECEIVED 최대 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        inference = "-" if r["inference"] is None else f'{r["inference"]:.0f}'
        queue = "-" if r["queue"] is None else r["queue"]
        lines.append(f'| {r["count"]} | {r["failed"]} | {r["submit"]:.2f} | {r["total"]:.2f} | {r["avg"]:.2f} | '
                     f'{r["p95"]:.2f} | {r["max"]:.2f} | {inference} | {queue} |')
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", default="http://localhost:8080")
    parser.add_argument("--counts", default="1,5,20", help="쉼표로 구분한 건수")
    parser.add_argument("--image", help="이미지 파일. 없으면 common.sh의 64x64 테스트 이미지")
    parser.add_argument("--mock-url", default="http://localhost:8090")
    parser.add_argument("--scenario", help="Mock 시나리오 고정, 끝나면 AUTO로 복구. 실제 AI면 지정하지 않음")
    parser.add_argument("--mysql-container", help="RECEIVED 건수를 조회할 MySQL 컨테이너 이름")
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()

    if args.image:
        image = Path(args.image).read_bytes()
    else:
        common = (Path(__file__).parent / "common.sh").read_text(encoding="utf-8")
        image = base64.b64decode(re.search(r"TEST_IMAGE_B64='([^']+)'", common).group(1))
    api = f'{args.backend.rstrip("/")}/api/v1'
    device, worker = login(api, "device-door", "Device1234!"), login(api, "worker01", "Worker1234!")

    def scenario(name):
        request("PUT", f"{args.mock_url}/mock/scenario", json.dumps({"scenario": name}).encode(),
                {"Content-Type": "application/json"})

    if args.scenario:
        scenario(args.scenario)
    try:
        rows = [measure(api, device, worker, image, int(n), args.mysql_container, args.wait_seconds)
                for n in args.counts.split(",")]
    finally:
        if args.scenario:
            scenario("AUTO")
    print(table(rows))


if __name__ == "__main__":
    main()
