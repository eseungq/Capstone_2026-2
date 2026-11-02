#!/bin/bash
# 시연 데이터 초기화: 개발 DB·저장소를 지우고 백엔드를 띄워 Mock 시나리오별 검사를 만듦
#   AUTO_PASS, REVIEW(사유별), FAILED, 재검사, 작업자 확인 완료. example-·mock- 모델·정책만 사용
# 사용: scripts/demo-reset.sh  (backend 폴더 기준으로 동작. y를 입력해야 진행)
#
# DB 초기화 방식
#   - compose 밖에서 만든 MySQL 컨테이너가 있으면 그 컨테이너의 DB만 지우고 다시 만듦 (포트는 컨테이너 설정을 따름)
#   - 없으면 docker compose down -v → up
# 환경 변수: MYSQL_CONTAINER(기본 inspection-mysql), STORAGE_ROOT(기본 ./storage), MOCK_URL(기본 http://localhost:8090),
#            BACKEND_URL(기본 http://localhost:8080)
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
cd "$SCRIPT_DIR/.."

MYSQL_CONTAINER="${MYSQL_CONTAINER:-inspection-mysql}"
STORAGE_ROOT="${STORAGE_ROOT:-./storage}"
MOCK_URL="${MOCK_URL:-http://localhost:8090}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8080}"
API="$BACKEND_URL/api/v1"
LOG_FILE="build/demo-backend.log"
IMAGE="${DEMO_IMAGE:-$(test_image)}"

die() {
    echo "[실패] $1"
    exit 1
}

echo "DB와 $STORAGE_ROOT 의 검사 데이터(연결 시험 결과 포함)가 모두 지워집니다."
printf '계속하려면 y 입력: '
read -r answer
[ "$answer" = "y" ] || { echo "취소했습니다."; exit 0; }

if curl -s -o /dev/null -m 2 "$BACKEND_URL/v3/api-docs"; then
    die "백엔드가 이미 실행 중입니다. 종료한 뒤 다시 실행하세요 ($BACKEND_URL)"
fi
http GET "$MOCK_URL/mock/scenario"
[ "$HTTP_STATUS" = "200" ] || die "Mock AI가 꺼져 있습니다: cd mock-ai && .venv/bin/uvicorn main:app --port 8090"

# 1) DB 초기화
mysql_root() {
    docker exec -i "$MYSQL_CONTAINER" mysql -uroot -proot "$@" 2>/dev/null
}
wait_mysql() {
    local i
    for i in $(seq 1 60); do
        docker exec "$MYSQL_CONTAINER" mysqladmin ping -h127.0.0.1 -uinspection -pinspection --silent >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}
COMPOSE_PROJECT="$(docker inspect "$MYSQL_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)"
if docker inspect "$MYSQL_CONTAINER" >/dev/null 2>&1 && [ -z "$COMPOSE_PROJECT" ]; then
    echo "== compose 밖의 컨테이너 $MYSQL_CONTAINER: DB만 다시 만듦"
    docker start "$MYSQL_CONTAINER" >/dev/null || die "컨테이너 시작 실패"
    wait_mysql || die "MySQL 응답 없음"
    mysql_root -e "DROP DATABASE IF EXISTS inspection; CREATE DATABASE inspection; GRANT ALL ON inspection.* TO 'inspection'@'%';" \
        || die "DB 초기화 실패"
    DB_PORT="$(docker port "$MYSQL_CONTAINER" 3306 | head -1 | sed 's/.*://')"
else
    echo "== docker compose down -v → up"
    docker compose down -v || die "docker compose down 실패"
    docker compose up -d || die "docker compose up 실패"
    wait_mysql || die "MySQL 응답 없음"
    DB_PORT=3306
fi

# 2) 저장소 정리 (down -v는 저장소를 지우지 않음)
rm -rf "$STORAGE_ROOT/original" "$STORAGE_ROOT/gradcam"

# 3) 백엔드 실행. Gradle 8.14는 JDK 25 이상에서 실행되지 않으므로 필요하면 낮은 JDK를 찾음
java_major="$(java -version 2>&1 | sed -nE '1s/.*version "([0-9]+).*/\1/p')"
if [ "${java_major:-0}" -ge 25 ] && [ -x /usr/libexec/java_home ]; then
    for version in 24 21 17; do
        if candidate="$(/usr/libexec/java_home -v "$version" 2>/dev/null)"; then
            export JAVA_HOME="$candidate"
            break
        fi
    done
fi
echo "== 백엔드 실행 (DB 포트 $DB_PORT, 로그 $LOG_FILE)"
mkdir -p build
DB_PORT="$DB_PORT" APP_STORAGE_LOCALROOT="$STORAGE_ROOT" nohup ./gradlew bootRun --console=plain > "$LOG_FILE" 2>&1 &
BACKEND_PID=$!
for i in $(seq 1 120); do
    curl -s -o /dev/null -m 2 "$BACKEND_URL/v3/api-docs" && break
    kill -0 "$BACKEND_PID" 2>/dev/null || die "백엔드 실행 실패. $LOG_FILE 확인"
    [ "$i" = "120" ] && die "백엔드가 2분 안에 뜨지 않음. $LOG_FILE 확인"
    sleep 1
done

# 4) 시연 데이터
DEVICE_TOKEN="$(login "$BACKEND_URL" "$DEVICE_ID" "$DEVICE_PW")"
WORKER_TOKEN="$(login "$BACKEND_URL" "$WORKER_ID" "$WORKER_PW")"
ADMIN_TOKEN="$(login "$BACKEND_URL" "$ADMIN_ID" "$ADMIN_PW")"
[ -n "$DEVICE_TOKEN" ] && [ -n "$WORKER_TOKEN" ] && [ -n "$ADMIN_TOKEN" ] || die "로그인 실패"

set_scenario() {
    http PUT "$MOCK_URL/mock/scenario" -H 'Content-Type: application/json' -d "{\"scenario\":\"$1\"}"
    [ "$HTTP_STATUS" = "200" ] || die "Mock 시나리오 $1 설정 실패"
}

# create 시나리오 → 분석이 끝난 검사 ID를 CREATED_ID에 저장
create() {
    set_scenario "$1"
    http POST "$API/inspections" -H "Authorization: Bearer $DEVICE_TOKEN" -F "image=@$IMAGE" -F partCode=DOOR
    CREATED_ID="$(json_get "$HTTP_BODY" '.data.inspectionId')"
    [ -n "$CREATED_ID" ] || die "접수 실패 $1: $HTTP_BODY"
    wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$CREATED_ID" 40 || die "분석 대기 시간 초과 $1"
    echo "  $1 → $(json_get "$HTTP_BODY" '.data.inspectionNo') $(json_get "$HTTP_BODY" '.data.displayState') $(json_get "$HTTP_BODY" '.data.policy.reviewReason')$(json_get "$HTTP_BODY" '.data.error.code')"
}

confirm() {
    http POST "$API/inspections/$1/confirm" -H "Authorization: Bearer $WORKER_TOKEN" \
        -H 'Content-Type: application/json' -d "{\"finalJudgement\":\"$2\",\"comment\":\"$3\"}"
    [ "$HTTP_STATUS" = "200" ] || die "confirm 실패: $HTTP_BODY"
    echo "  confirm $2 → $1"
}

echo "== 시연 데이터 생성"
create GOOD_CALIBRATED
create GOOD_CALIBRATED
create GOOD_ABOVE_THRESHOLD
create GOOD_UNCALIBRATED
create DEFECT_GRADCAM
create DEFECT_GRADCAM_JPEG
create DEFECT_NO_ACTIVATION
create DEFECT_GRADCAM_FAIL

# 작업자 확인 완료 건
create DEFECT_GRADCAM
confirm "$CREATED_ID" FAIL "시연: 불량 확인"
create GOOD_ABOVE_THRESHOLD
confirm "$CREATED_ID" PASS "시연: 정상 확인"

# 정책을 잠시 중지해 NO_ACTIVE_POLICY 사유를 만듦
http GET "$API/admin/policies?partCode=DOOR&active=true" -H "Authorization: Bearer $ADMIN_TOKEN"
POLICY_ID="$(json_get "$HTTP_BODY" '.data[0].policyId')"
[ -n "$POLICY_ID" ] || die "예시 정책을 찾지 못함"
http POST "$API/admin/policies/$POLICY_ID/deactivate" -H "Authorization: Bearer $ADMIN_TOKEN"
create GOOD_CALIBRATED
http POST "$API/admin/policies/$POLICY_ID/activate" -H "Authorization: Bearer $ADMIN_TOKEN"
[ "$HTTP_STATUS" = "200" ] || die "예시 정책 다시 적용 실패: $HTTP_BODY"

# FAILED 건: 재검사하지 않은 것과 재검사한 것
create ERROR_5XX
create ERROR_4XX
create INVALID_RESPONSE
create ERROR_5XX
FAILED_ID="$CREATED_ID"
set_scenario GOOD_CALIBRATED
http POST "$API/inspections/$FAILED_ID/retry" -H "Authorization: Bearer $WORKER_TOKEN"
RETRY_ID="$(json_get "$HTTP_BODY" '.data.inspectionId')"
[ -n "$RETRY_ID" ] || die "재검사 실패: $HTTP_BODY"
wait_finished "$BACKEND_URL" "$WORKER_TOKEN" "$RETRY_ID" 40 || die "재검사 대기 시간 초과"
echo "  재검사 → $(json_get "$HTTP_BODY" '.data.inspectionNo') $(json_get "$HTTP_BODY" '.data.displayState') (원래 $FAILED_ID)"
set_scenario AUTO

# 5) 결과
echo "== 상태별 건수"
docker exec "$MYSQL_CONTAINER" mysql -uinspection -pinspection inspection -t -e "
    SELECT status, recommended_action AS action, review_reason AS reason, error_code AS error,
           COUNT(*) AS cnt, SUM(final_judgement IS NOT NULL AND judged_by = 'WORKER') AS confirmed,
           SUM(retry_of_inspection_id IS NOT NULL) AS retried
    FROM inspection GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;" 2>/dev/null
echo
echo "백엔드는 계속 실행 중입니다 (PID $BACKEND_PID). 종료: kill $BACKEND_PID"
