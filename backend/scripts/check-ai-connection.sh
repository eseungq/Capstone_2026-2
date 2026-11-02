#!/bin/bash
# 실제 AI 연결 점검 (계약 v4 7장). 단계별 OK/실패와 원인 추정을 출력
# 사용: scripts/check-ai-connection.sh <AI 주소> <백엔드 공개 주소> [이미지 파일]
#   예: scripts/check-ai-connection.sh http://100.64.0.2:8000 http://100.64.0.1:8080 door.jpg
set -u
source "$(dirname "$0")/common.sh"

if [ $# -lt 2 ]; then
    echo "사용: $0 <AI 주소> <백엔드 공개 주소> [이미지 파일]"
    exit 2
fi
AI_URL="${1%/}"
BACKEND_URL="${2%/}"
IMAGE="${3:-$(test_image)}"
FAILED=0

ok() { echo "[OK]   $1"; }
ng() { echo "[실패] $1"; FAILED=1; }
hint() { echo "       → $1"; }

echo "== 1. 백엔드 응답"
http GET "$BACKEND_URL/v3/api-docs"
if [ "$HTTP_STATUS" = "200" ]; then
    ok "$BACKEND_URL"
else
    ng "$BACKEND_URL (HTTP $HTTP_STATUS)"
    hint "bootRun 실행 여부, 주소·포트, macOS 방화벽의 Java 허용, Tailscale 연결을 확인"
    exit 1
fi

echo "== 2. 백엔드 쪽 모델 상태"
WORKER_TOKEN="$(login "$BACKEND_URL" "$WORKER_ID" "$WORKER_PW")"
ACTIVE_MODEL=""
if [ -n "$WORKER_TOKEN" ]; then
    http GET "$BACKEND_URL/api/v1/parts" -H "Authorization: Bearer $WORKER_TOKEN"
    # 부품은 partCode 순서로 오므로 DOOR를 찾아 활성 모델을 읽음
    index=0
    while :; do
        code="$(json_get "$HTTP_BODY" ".data[$index].partCode")"
        [ -z "$code" ] && break
        if [ "$code" = "DOOR" ]; then
            ACTIVE_MODEL="$(json_get "$HTTP_BODY" ".data[$index].items[0].activeModelVersion")"
            break
        fi
        index=$((index + 1))
    done
    if [ -n "$ACTIVE_MODEL" ]; then
        ok "DOOR 활성 모델: $ACTIVE_MODEL"
    else
        ng "DOOR 활성 모델 없음"
        hint "README \"실제 AI 연결\"의 모델 전환 SQL을 확인"
    fi
else
    ng "WORKER 로그인 실패"
    hint "백엔드 DB에 시드 계정이 있는지, 잠기지 않았는지 확인 (WORKER_ID·WORKER_PW로 변경 가능)"
fi

echo "== 3. Mac → AI: $AI_URL/internal/v1/models"
http GET "$AI_URL/internal/v1/models"
case "$HTTP_STATUS" in
    200)
        if [ -n "$ACTIVE_MODEL" ] && printf '%s' "$HTTP_BODY" | grep -q "\"$ACTIVE_MODEL\""; then
            ok "응답에 활성 모델이 있음"
        elif [ -n "$ACTIVE_MODEL" ]; then
            ng "응답에 활성 모델 $ACTIVE_MODEL 이 없음 (접수하면 422 또는 형식 불일치)"
            hint "AI에 올라간 모델 버전과 DB의 모델 버전을 비교. 응답 원문: $(printf '%s' "$HTTP_BODY" | cut -c1-300)"
        else
            ok "응답 받음: $(printf '%s' "$HTTP_BODY" | cut -c1-300)"
        fi
        ;;
    404)
        ng "엔드포인트 없음 (HTTP 404)"
        hint "실제 AI에 이 경로가 없으면 백엔드를 APP_AI_MODELCHECKENABLED=false 로 실행. 접수는 계속 시도함"
        ;;
    000)
        ng "연결 실패: $(cat "$WORK_DIR/curl-error")"
        hint "AI 서버 실행 여부, 포트, Tailscale 연결을 확인. 접수는 계속 시도함 (FAILED가 예상됨)"
        ;;
    *)
        ng "HTTP $HTTP_STATUS: $(printf '%s' "$HTTP_BODY" | cut -c1-300)"
        ;;
esac

echo "== 4. AI → 백엔드 (DGX에서 직접 실행)"
echo "       curl -s -o /dev/null -w '%{http_code}\\n' $BACKEND_URL/v3/api-docs     # 200이면 정상"

echo "== 5. 사진 접수 (DEVICE)"
DEVICE_TOKEN="$(login "$BACKEND_URL" "$DEVICE_ID" "$DEVICE_PW")"
if [ -z "$DEVICE_TOKEN" ]; then
    ng "DEVICE 로그인 실패"
    hint "백엔드 DB에 시드 계정이 있는지, 잠기지 않았는지 확인 (DEVICE_ID·DEVICE_PW로 변경 가능)"
    exit 1
fi
http POST "$BACKEND_URL/api/v1/inspections" -H "Authorization: Bearer $DEVICE_TOKEN" \
    -F "image=@$IMAGE" -F partCode=DOOR
INSPECTION_ID="$(json_get "$HTTP_BODY" '.data.inspectionId')"
if [ "$HTTP_STATUS" = "202" ] && [ -n "$INSPECTION_ID" ]; then
    ok "접수 $(json_get "$HTTP_BODY" '.data.inspectionNo') ($INSPECTION_ID)"
else
    ng "접수 실패 HTTP $HTTP_STATUS traceId=$HTTP_TRACE: $HTTP_BODY"
    hint "422 MODEL_NOT_AVAILABLE이면 AI 목록에 활성 모델이 없거나 loadable=false"
    exit 1
fi

echo "== 6. 분석 결과 (최대 ${ANALYSIS_WAIT_SECONDS:-60}초)"
if ! wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$INSPECTION_ID" "${ANALYSIS_WAIT_SECONDS:-60}"; then
    ng "시간 초과. 마지막 응답: $(printf '%s' "$HTTP_BODY" | cut -c1-300)"
    exit 1
fi
DETAIL="$HTTP_BODY"
STATUS="$(json_get "$DETAIL" '.data.status')"
IMAGE_URL="$(json_get "$DETAIL" '.data.images.original.url')"
echo "       status=$STATUS predictedQuality=$(json_get "$DETAIL" '.data.ai.predictedQuality')"
echo "       modelVersion=$(json_get "$DETAIL" '.data.ai.modelVersion')"
echo "       reviewReason=$(json_get "$DETAIL" '.data.policy.reviewReason') gradcamStatus=$(json_get "$DETAIL" '.data.images.gradcamStatus') inferenceTimeMs=$(json_get "$DETAIL" '.data.ai.inferenceTimeMs')"
if [ "$STATUS" = "COMPLETED" ]; then
    ok "분석 완료"
else
    ERROR_CODE="$(json_get "$DETAIL" '.data.error.code')"
    ng "FAILED $ERROR_CODE"
    case "$ERROR_CODE" in
        AI_SERVER_ERROR) hint "AI 서버 연결 실패 또는 5xx. AI 주소(APP_AI_BASEURL)와 AI 서버 로그를 확인" ;;
        AI_SERVER_TIMEOUT) hint "응답 시간 초과. APP_AI_READTIMEOUTMS(기본 10000)를 실측값에 맞춰 조정" ;;
        AI_REQUEST_REJECTED) hint "AI가 4xx로 거절. 이미지 다운로드 실패라면 PUBLIC_BASE_URL이 DGX에서 접근 가능한 주소인지 확인" ;;
        AI_RESPONSE_INVALID) hint "응답 형식이 계약 7.2와 다름. 백엔드 로그에서 traceId로 원인을 확인" ;;
    esac
fi

echo "== 7. 이미지 주소 (DGX에서 직접 실행, 10분 안에)"
case "$IMAGE_URL" in
    "$BACKEND_URL"/*)
        ok "서명 주소가 백엔드 공개 주소로 시작함" ;;
    *)
        ng "서명 주소가 공개 주소와 다름: $IMAGE_URL"
        hint "PUBLIC_BASE_URL=$BACKEND_URL 로 백엔드를 다시 실행" ;;
esac
echo "       curl -s -o /dev/null -w '%{http_code}\\n' '$IMAGE_URL'     # 200이면 정상"

echo
if [ "$FAILED" = "0" ]; then
    echo "결과: 모두 통과. 4·7번 명령은 DGX에서 따로 확인"
else
    echo "결과: 실패 항목 있음"
fi
exit "$FAILED"
