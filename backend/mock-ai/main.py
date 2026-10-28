"""
Mock AI 추론 서버 (백엔드 API 계약 v4 7장 규격)

실제 모델 없이 백엔드의 접수 → 분석 → 판정 저장 흐름을 시험하기 위한 서버.
값은 전부 가짜이며 AI 성능·정책 검증 결과가 아니다. 모델 버전은 mock- 접두어.

실행: uvicorn main:app --port 8090
시나리오 바꾸기: curl -X PUT localhost:8090/mock/scenario -H 'Content-Type: application/json' -d '{"scenario":"DEFECT_GRADCAM"}'
"""
import asyncio
import base64
import hashlib
import io
import math
import os
import time
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

MODELS = {
    # modelVersion: (partCode, calibratorVersion)
    "mock-door-swin-t-v1": ("DOOR", "mock-cal-v1"),
}

# 시나리오별 반환 값. raw ≥ 0.5 이면 DEFECT (계약 7.2)
SCENARIOS = {
    "GOOD_CALIBRATED": dict(quality="GOOD", raw=0.123456, cal=0.021000, calibrated=True),   # 예시 정책(0.05) 기준 AUTO_PASS
    "GOOD_ABOVE_THRESHOLD": dict(quality="GOOD", raw=0.312345, cal=0.200000, calibrated=True),  # REVIEW(ABOVE_THRESHOLD)
    "GOOD_UNCALIBRATED": dict(quality="GOOD", raw=0.231044, cal=None, calibrated=False),  # REVIEW(CALIBRATION_UNAVAILABLE)
    "DEFECT_GRADCAM": dict(quality="DEFECT", raw=0.912345, cal=0.880000, calibrated=True, gradcam=True),
    "DEFECT_GRADCAM_FAIL": dict(quality="DEFECT", raw=0.871234, cal=0.830000, calibrated=True, gradcam=False),
    "ERROR_4XX": dict(error=422),        # 백엔드: AI_REQUEST_REJECTED → FAILED (재시도 없음)
    "ERROR_5XX": dict(error=500),        # 백엔드: 1회 재시도 후 AI_SERVER_ERROR → FAILED
    # 백엔드 read-timeout(10초)보다 오래 대기 후 정상 응답 → 백엔드는 이미 AI_SERVER_TIMEOUT으로 FAILED (늦은 결과 무시)
    "TIMEOUT": dict(quality="GOOD", raw=0.123456, cal=0.021000, calibrated=True, timeout=True),
    # modelVersion 불일치 → AI_RESPONSE_INVALID
    "INVALID_RESPONSE": dict(quality="GOOD", raw=0.123456, cal=0.021000, calibrated=True, invalid=True),
}
# AUTO: 사진 내용(해시)으로 정상 시나리오 중 하나를 고름. 같은 사진은 항상 같은 결과
AUTO_POOL = ["GOOD_CALIBRATED", "GOOD_ABOVE_THRESHOLD", "GOOD_UNCALIBRATED", "DEFECT_GRADCAM", "DEFECT_GRADCAM_FAIL"]

TIMEOUT_SECONDS = float(os.getenv("MOCK_TIMEOUT_SECONDS", "15"))
DELAY_MS = int(os.getenv("MOCK_DELAY_MS", "300"))  # 추론 시간 흉내

state = {"scenario": os.getenv("MOCK_SCENARIO", "AUTO"), "once": None}

app = FastAPI(title="Mock AI 추론 서버", version="v4-mock")


class PredictRequest(BaseModel):
    inspectionId: Optional[str] = None
    partCode: Optional[str] = None
    requestedModelVersion: Optional[str] = None
    imageUrl: Optional[str] = None


class ScenarioRequest(BaseModel):
    scenario: str
    once: bool = False  # true면 다음 요청 1건에만 적용


def error_body(status: int, code: str, message: str, inspection_id: Optional[str]):
    # AI 오류 본문도 공통 형식 (합의 10/15)
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "traceId": uuid.uuid4().hex[:16], "inspectionId": inspection_id}})


@app.get("/internal/v1/models")
def models():
    return {"data": [{"modelVersion": v, "partCode": p, "calibratorVersion": c, "loadable": True}
                     for v, (p, c) in MODELS.items()]}


@app.get("/mock/scenario")
def get_scenario():
    return {"scenario": state["scenario"], "once": state["once"], "available": ["AUTO", *SCENARIOS.keys()]}


@app.put("/mock/scenario")
def set_scenario(req: ScenarioRequest):
    name = req.scenario.upper()
    if name != "AUTO" and name not in SCENARIOS:
        return JSONResponse(status_code=400, content={"error": f"unknown scenario {name}",
                                                      "available": ["AUTO", *SCENARIOS.keys()]})
    if req.once:
        state["once"] = name
    else:
        state["scenario"], state["once"] = name, None
    return get_scenario()


def pick_scenario(image_bytes: bytes) -> str:
    if state["once"]:
        name, state["once"] = state["once"], None
        return name
    if state["scenario"] != "AUTO":
        return state["scenario"]
    digest = hashlib.sha256(image_bytes).digest()
    return AUTO_POOL[digest[0] % len(AUTO_POOL)]


def make_gradcam(img: Image.Image, seed: bytes) -> bytes:
    """원본 위에 가짜 히트맵을 겹친 PNG. 원본(방향 보정 후)과 같은 크기 (계약 7.2)"""
    w, h = img.size
    # 계산량을 줄이려고 작은 크기에서 히트맵을 만든 뒤 원본 크기로 확대
    sw, sh = max(1, w // 8), max(1, h // 8)
    cx, cy = (0.25 + 0.5 * seed[1] / 255) * sw, (0.25 + 0.5 * seed[2] / 255) * sh
    radius = 0.25 * min(sw, sh) + 1
    heat = Image.new("RGB", (sw, sh))
    px = heat.load()
    for y in range(sh):
        for x in range(sw):
            v = math.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2 * radius ** 2)))  # 0~1
            # 파랑 → 초록 → 빨강 (jet 근사)
            r = int(255 * min(1, max(0, 1.5 - abs(4 * v - 3))))
            g = int(255 * min(1, max(0, 1.5 - abs(4 * v - 2))))
            b = int(255 * min(1, max(0, 1.5 - abs(4 * v - 1))))
            px[x, y] = (r, g, b)
    heat = heat.resize((w, h), Image.BILINEAR)
    overlay = Image.blend(img.convert("RGB"), heat, 0.45)
    buf = io.BytesIO()
    overlay.save(buf, format="PNG")
    return buf.getvalue()


@app.post("/internal/v1/predict")
async def predict(req: PredictRequest, request: Request):
    started = time.perf_counter()
    iid = req.inspectionId
    if not iid or not req.requestedModelVersion or not req.imageUrl or not req.partCode:
        return error_body(400, "INVALID_REQUEST", "inspectionId·partCode·requestedModelVersion·imageUrl 필수", iid)
    if req.requestedModelVersion not in MODELS:
        return error_body(422, "MODEL_VERSION_NOT_FOUND", f"모델 버전 없음: {req.requestedModelVersion}", iid)
    part, calibrator = MODELS[req.requestedModelVersion]
    if part != req.partCode:
        return error_body(422, "PART_MODEL_MISMATCH", f"{req.requestedModelVersion}는 {part} 모델", iid)

    # 이미지 읽기 (백엔드가 준 만료 주소)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(req.imageUrl)
        if res.status_code != 200:
            return error_body(422, "IMAGE_UNREADABLE", f"이미지 다운로드 실패 HTTP {res.status_code}", iid)
        image_bytes = res.content
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes)))  # 학습과 같은 EXIF 방향 처리
        img.load()
    except Exception as e:  # noqa: BLE001
        return error_body(422, "IMAGE_UNREADABLE", f"이미지를 읽을 수 없음: {e}", iid)

    name = pick_scenario(image_bytes)
    s = SCENARIOS[name]
    print(f"[mock-ai] {iid} scenario={name}", flush=True)

    if s.get("timeout"):
        await asyncio.sleep(TIMEOUT_SECONDS)
    if s.get("error") == 500:
        return error_body(500, "MODEL_RUNTIME_ERROR", "Mock: 추론 중 내부 오류", iid)
    if s.get("error") == 422:
        return error_body(422, "IMAGE_UNREADABLE", "Mock: 요청 거절 시나리오", iid)

    await asyncio.sleep(DELAY_MS / 1000)
    gradcam = None
    if s.get("gradcam"):
        png = make_gradcam(img, hashlib.sha256(image_bytes).digest())
        gradcam = {"targetClass": "DEFECT", "format": "png", "imageBase64": base64.b64encode(png).decode()}

    body = {
        "inspectionId": iid,
        "modelVersion": req.requestedModelVersion,
        "predictedQuality": s["quality"],
        "rawDefectProbability": s["raw"],
        "calibratedDefectProbability": s["cal"] if s["calibrated"] else None,
        "calibratorVersion": calibrator if s["calibrated"] else None,
        "imageWidth": img.size[0],
        "imageHeight": img.size[1],
        "gradcam": gradcam,
        "inferenceTimeMs": int((time.perf_counter() - started) * 1000),
    }
    if s.get("invalid"):
        body["modelVersion"] = "mock-wrong-version"
    return body
