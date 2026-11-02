#!/bin/bash
# 점검 스크립트 공통 함수 (macOS 기본 bash 3.2 + curl). JSON은 jq, 없으면 python3로 읽음
# 다른 스크립트에서 source 해서 사용

WORKER_ID="${WORKER_ID:-worker01}"; WORKER_PW="${WORKER_PW:-Worker1234!}"
ADMIN_ID="${ADMIN_ID:-admin01}"; ADMIN_PW="${ADMIN_PW:-Admin1234!}"
DEVICE_ID="${DEVICE_ID:-device-door}"; DEVICE_PW="${DEVICE_PW:-Device1234!}"
TEST_IMAGE_B64='iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAgElEQVR4nNXOQREAIAzAsFKZKEEJehGxB9coyNrnUiZxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEufvwNQDG+QB6OIGLqEAAAAASUVORK5CYII='

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/inspection-script.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

# json_get '<JSON>' '.data.items[0].id' → 값 (없거나 null이면 빈 문자열)
json_get() {
    if command -v jq >/dev/null 2>&1; then
        printf '%s' "$1" | jq -r "$2 | if . == null then empty else . end" 2>/dev/null
    elif command -v python3 >/dev/null 2>&1; then
        printf '%s' "$1" | python3 -c '
import json, re, sys
try:
    v = json.load(sys.stdin)
    for key, idx in re.findall(r"\.([A-Za-z0-9_]+)|\[(\d+)\]", sys.argv[1]):
        v = v[key] if key else v[int(idx)]
except Exception:
    sys.exit(0)
if v is None:
    sys.exit(0)
print(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else (str(v).lower() if isinstance(v, bool) else v))
' "$2"
    else
        echo "jq 또는 python3가 필요합니다" >&2
        exit 2
    fi
}

# http METHOD URL [curl 인자...] → HTTP_STATUS, HTTP_BODY, HTTP_TRACE 설정. 연결 실패면 HTTP_STATUS=000
http() {
    local method="$1" url="$2"
    shift 2
    HTTP_STATUS=$(curl -sS -g -m "${HTTP_TIMEOUT:-30}" -o "$WORK_DIR/body" -D "$WORK_DIR/headers" -w '%{http_code}' \
        -X "$method" "$url" "$@" 2>"$WORK_DIR/curl-error") || HTTP_STATUS=000
    HTTP_BODY="$(cat "$WORK_DIR/body" 2>/dev/null)"
    HTTP_TRACE="$(tr -d '\r' < "$WORK_DIR/headers" 2>/dev/null | awk -F': ' 'tolower($1)=="x-trace-id"{print $2}')"
    : > "$WORK_DIR/body"
    : > "$WORK_DIR/headers"
}

# login 기준주소 아이디 비밀번호 → Access Token 출력 (실패하면 빈 문자열)
login() {
    http POST "$1/api/v1/auth/login" -H 'Content-Type: application/json' \
        -d "{\"loginId\":\"$2\",\"password\":\"$3\"}"
    json_get "$HTTP_BODY" '.data.accessToken'
}

# 테스트 이미지 파일 경로 출력 (64x64 PNG)
test_image() {
    local path="$WORK_DIR/test.png"
    [ -f "$path" ] || printf '%s' "$TEST_IMAGE_B64" | base64 -D > "$path" 2>/dev/null \
        || printf '%s' "$TEST_IMAGE_B64" | base64 -d > "$path"
    echo "$path"
}

# wait_finished 기준주소 토큰 검사ID [제한초] → 끝난 상세를 HTTP_BODY에 남김. 시간 초과면 1
wait_finished() {
    local deadline=$((SECONDS + ${4:-60})) status
    while [ "$SECONDS" -lt "$deadline" ]; do
        http GET "$1/api/v1/inspections/$3" -H "Authorization: Bearer $2"
        status="$(json_get "$HTTP_BODY" '.data.status')"
        if [ "$status" = "COMPLETED" ] || [ "$status" = "FAILED" ]; then
            return 0
        fi
        sleep 1
    done
    return 1
}
