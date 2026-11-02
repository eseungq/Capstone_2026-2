#!/bin/bash
# 전체 흐름 점검: 정상(접수 → 판정 → 표시 → 작업자 확인 → 이력), 오류(FAILED → 재검사)
# 사용: scripts/e2e-flow.sh [백엔드 주소] [mock|real]
#   mock  Mock AI 시나리오를 바꿔 정상·오류 흐름을 모두 실행 (MOCK_URL, 기본 http://localhost:8090)
#   real  시나리오 변경 없이 정상 흐름만 실행, 오류 흐름은 수동 명령을 출력. 실제 사진은 IMAGE=파일 경로로 지정
set -u
source "$(dirname "$0")/common.sh"

BACKEND_URL="${1:-http://localhost:8080}"
BACKEND_URL="${BACKEND_URL%/}"
MODE="${2:-mock}"
MOCK_URL="${MOCK_URL:-http://localhost:8090}"
API="$BACKEND_URL/api/v1"
IMAGE="${IMAGE:-$(test_image)}"
if [ "$MODE" != "mock" ] && [ "$MODE" != "real" ]; then
    echo "사용: $0 [백엔드 주소] [mock|real]"
    exit 2
fi

STEP_COUNT=0
FAIL_COUNT=0
SUMMARY=""

ok() {
    STEP_COUNT=$((STEP_COUNT + 1))
    SUMMARY="$SUMMARY
[OK]   $1"
    echo "[OK]   $1"
}

# 실패 단계: 응답 본문과 traceId 출력
ng() {
    STEP_COUNT=$((STEP_COUNT + 1))
    FAIL_COUNT=$((FAIL_COUNT + 1))
    SUMMARY="$SUMMARY
[실패] $1"
    echo "[실패] $1"
    echo "       HTTP $HTTP_STATUS traceId=$HTTP_TRACE"
    echo "       $(printf '%s' "$HTTP_BODY" | cut -c1-400)"
}

finish() {
    echo
    echo "== 요약 (모드: $MODE, 실패 $FAIL_COUNT / 전체 $STEP_COUNT)$SUMMARY"
    if [ "$FAIL_COUNT" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

set_scenario() {
    [ "$MODE" = "mock" ] || return 0
    http PUT "$MOCK_URL/mock/scenario" -H 'Content-Type: application/json' -d "{\"scenario\":\"$1\"}"
    if [ "$HTTP_STATUS" = "200" ]; then
        ok "Mock 시나리오 $1"
    else
        ng "Mock 시나리오 $1 (Mock AI 실행 여부, MOCK_URL 확인)"
        finish
    fi
}

# 접수 후 검사 ID를 INSPECTION_ID에 저장
submit() {
    INSPECTION_ID=""
    http POST "$API/inspections" -H "Authorization: Bearer $DEVICE_TOKEN" -F "image=@$IMAGE" -F partCode=DOOR
    INSPECTION_ID="$(json_get "$HTTP_BODY" '.data.inspectionId')"
    if [ "$HTTP_STATUS" = "202" ] && [ -n "$INSPECTION_ID" ]; then
        ok "접수 202 $(json_get "$HTTP_BODY" '.data.inspectionNo')"
    else
        ng "접수 (202 기대)"
        finish
    fi
}

# 확인 필요 목록 전체에서 ID를 찾음 (오래된 순이라 커서로 끝까지 확인)
queue_contains() {
    local cursor="" args
    while :; do
        args="size=100"
        [ -n "$cursor" ] && args="$args&cursor=$cursor"
        http GET "$API/monitoring/queue?$args" -H "Authorization: Bearer $WORKER_TOKEN"
        if printf '%s' "$HTTP_BODY" | grep -q "$1"; then
            return 0
        fi
        cursor="$(json_get "$HTTP_BODY" '.data.nextCursor')"
        [ -n "$cursor" ] || return 1
    done
}

echo "== 로그인"
DEVICE_TOKEN="$(login "$BACKEND_URL" "$DEVICE_ID" "$DEVICE_PW")"
WORKER_TOKEN="$(login "$BACKEND_URL" "$WORKER_ID" "$WORKER_PW")"
if [ -n "$DEVICE_TOKEN" ] && [ -n "$WORKER_TOKEN" ]; then
    ok "DEVICE·WORKER 로그인"
else
    HTTP_STATUS="-"; HTTP_TRACE="-"; HTTP_BODY="토큰을 받지 못함. 백엔드 실행 여부와 계정을 확인"
    ng "로그인"
    finish
fi

echo "== 정상 흐름"
set_scenario GOOD_ABOVE_THRESHOLD   # AUTO_PASS면 confirm이 409이므로 REVIEW 고정
submit
ID="$INSPECTION_ID"
if ! wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$ID" "${ANALYSIS_WAIT_SECONDS:-60}"; then
    ng "분석 완료 대기 시간 초과"
    finish
fi
DISPLAY_STATE="$(json_get "$HTTP_BODY" '.data.displayState')"
if [ "$(json_get "$HTTP_BODY" '.data.status')" = "COMPLETED" ] && [ "$DISPLAY_STATE" = "REVIEW_PENDING" ]; then
    ok "COMPLETED · REVIEW_PENDING ($(json_get "$HTTP_BODY" '.data.policy.reviewReason'))"
else
    ng "COMPLETED · REVIEW_PENDING 기대, 실제 $DISPLAY_STATE"
    finish
fi

http GET "$API/monitoring/parts" -H "Authorization: Bearer $WORKER_TOKEN"
if printf '%s' "$HTTP_BODY" | grep -q "$ID"; then
    ok "/monitoring/parts 최근 목록에 표시"
else
    ng "/monitoring/parts에 없음"
fi
if queue_contains "$ID"; then
    ok "/monitoring/queue에 표시"
else
    ng "/monitoring/queue에 없음"
fi

http POST "$API/inspections/$ID/confirm" -H "Authorization: Bearer $WORKER_TOKEN" \
    -H 'Content-Type: application/json' -d '{"finalJudgement":"PASS","comment":"e2e 점검"}'
if [ "$HTTP_STATUS" = "200" ]; then
    ok "confirm 200"
else
    ng "confirm (200 기대)"
fi

http GET "$API/inspections?partCode=DOOR&displayState=REVIEW_DONE&size=100" -H "Authorization: Bearer $WORKER_TOKEN"
if printf '%s' "$HTTP_BODY" | grep -q "$ID"; then
    ok "이력에서 REVIEW_DONE 확인"
else
    ng "이력의 REVIEW_DONE에 없음"
fi

echo "== 오류 흐름"
if [ "$MODE" = "real" ]; then
    echo "real 모드는 AI 시나리오를 바꿀 수 없어 수동으로 확인 (통합 점검표 E2)"
    echo "  1) AI 서버를 끈 뒤 접수 → 202, 잠시 후 상세가 FAILED · AI_SERVER_ERROR"
    echo "     scripts/check-ai-connection.sh <AI 주소> $BACKEND_URL"
    echo "  2) AI 서버를 켠 뒤 재검사 → 202, 새 검사 COMPLETED, 원래 건은 FAILED 유지"
    echo "     curl -X POST $API/inspections/<FAILED 건 ID>/retry -H \"Authorization: Bearer <WORKER 토큰>\""
    finish
fi

set_scenario ERROR_5XX              # once 없이 설정해야 재시도까지 실패해 FAILED
submit
FAILED_ID="$INSPECTION_ID"
if ! wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$FAILED_ID" "${ANALYSIS_WAIT_SECONDS:-60}"; then
    ng "FAILED 대기 시간 초과"
    set_scenario AUTO
    finish
fi
ERROR_CODE="$(json_get "$HTTP_BODY" '.data.error.code')"
if [ "$(json_get "$HTTP_BODY" '.data.status')" = "FAILED" ] && [ "$ERROR_CODE" = "AI_SERVER_ERROR" ]; then
    ok "FAILED · AI_SERVER_ERROR"
else
    ng "FAILED · AI_SERVER_ERROR 기대"
fi
echo "       알림 확인: 백엔드 로그에서 '[알림 로그] ANALYSIS_FAILED $(json_get "$HTTP_BODY" '.data.inspectionNo')' (app.push.enabled=false일 때)"
if queue_contains "$FAILED_ID"; then
    ok "FAILED 건이 /monitoring/queue에 표시"
else
    ng "FAILED 건이 /monitoring/queue에 없음"
fi

set_scenario GOOD_CALIBRATED        # Mock 정상 복구
http POST "$API/inspections/$FAILED_ID/retry" -H "Authorization: Bearer $WORKER_TOKEN"
RETRY_ID="$(json_get "$HTTP_BODY" '.data.inspectionId')"
if [ "$HTTP_STATUS" = "202" ] && [ -n "$RETRY_ID" ]; then
    ok "retry 202"
else
    ng "retry (202 기대)"
    set_scenario AUTO
    finish
fi
if wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$RETRY_ID" "${ANALYSIS_WAIT_SECONDS:-60}" \
    && [ "$(json_get "$HTTP_BODY" '.data.status')" = "COMPLETED" ]; then
    ok "재검사 새 검사 COMPLETED"
else
    ng "재검사 COMPLETED 기대"
fi
http GET "$API/inspections/$FAILED_ID" -H "Authorization: Bearer $WORKER_TOKEN"
if [ "$(json_get "$HTTP_BODY" '.data.status')" = "FAILED" ]; then
    ok "원래 건 FAILED 유지"
else
    ng "원래 건 FAILED 유지 기대"
fi
if queue_contains "$FAILED_ID"; then
    ng "재검사한 FAILED 건이 /monitoring/queue에 남아 있음"
else
    ok "재검사한 FAILED 건은 /monitoring/queue에서 제외"
fi
set_scenario AUTO
finish
