package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 6.12 판정 확인 요청·정정. 최초 판정(inspection.final_judgement·judged_by)은 바꾸지 않고 별도 기록
//   DB는 다른 테스트와 공유하므로 이 테스트가 만든 ID만 걸러서 확인
class JudgementRequestIntegrationTest extends IntegrationTestBase {

    private static final String SECOND_WORKER = "worker-jr2";
    private static String secondWorkerToken;

    private String autoPass() throws Exception {
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("AUTO_PASS");
        return detail.path("inspectionId").asText();
    }

    // 작업자가 확인한 REVIEW 건 (judgedBy = WORKER)
    private String reviewConfirmed() throws Exception {
        ai = goodAboveThreshold();
        String id = submitAndWait().path("inspectionId").asText();
        assertThat(postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", "FAIL"), worker())
                .getResponse().getStatus()).isEqualTo(200);
        ai = goodBelowThreshold();
        return id;
    }

    // 두 번째 작업자 계정 (worker01과 같은 비밀번호). 공유 DB라 이미 있으면 그대로 씀
    private String secondWorker() throws Exception {
        if (secondWorkerToken == null) {
            jdbc.update("""
                    insert ignore into users (id, login_id, password_hash, role, failed_login_count, locked, created_at)
                    select UUID(), ?, password_hash, 'WORKER', 0, false, NOW(6) from users where login_id = 'worker01'""",
                    SECOND_WORKER);
            MvcResult result = mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                    .content(mapper.writeValueAsString(Map.of("loginId", SECOND_WORKER, "password", "Worker1234!"))))
                    .andReturn();
            secondWorkerToken = json(result).at("/data/accessToken").asText();
        }
        return secondWorkerToken;
    }

    private MvcResult request(String inspectionId, String claimed, String reason, String token) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("claimedJudgement", claimed);
        body.put("area", "고정핀");
        body.put("reason", reason);
        return postJson("/api/v1/inspections/" + inspectionId + "/judgement-requests", body, token);
    }

    private String openRequest(String inspectionId, String claimed) throws Exception {
        MvcResult result = request(inspectionId, claimed, "실물 확인 결과 다름", worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).at("/data/requestId").asText();
    }

    private MvcResult resolve(String requestId, String decision, String note, String token) throws Exception {
        return postJson("/api/v1/admin/judgement-requests/" + requestId + "/resolve",
                Map.of("decision", decision, "note", note), token);
    }

    private JsonNode detail(String inspectionId) throws Exception {
        return json(call(get("/api/v1/inspections/{id}", inspectionId), worker())).path("data");
    }

    private JsonNode historyItem(String inspectionId) throws Exception {
        JsonNode items = json(call(get("/api/v1/inspections?size=100"), worker())).at("/data/items");
        return StreamSupport.stream(items.spliterator(), false)
                .filter(n -> n.path("inspectionId").asText().equals(inspectionId)).findFirst()
                .orElseThrow(() -> new AssertionError("이력에 없음: " + inspectionId));
    }

    // 목록에서 주어진 요청 ID만 순서대로
    private List<String> listed(String query, List<String> requestIds) throws Exception {
        JsonNode items = json(call(get("/api/v1/admin/judgement-requests?size=100&" + query), admin()))
                .at("/data/items");
        List<String> ids = new ArrayList<>();
        items.forEach(n -> {
            if (requestIds.contains(n.path("requestId").asText())) {
                ids.add(n.path("requestId").asText());
            }
        });
        return ids;
    }

    private Map<String, Object> inspectionRow(String inspectionId) {
        return jdbc.queryForMap("select final_judgement, judged_by from inspection where id = ?", inspectionId);
    }

    @Test
    @DisplayName("AUTO_PASS 건 요청: 201, 요청 형식 그대로, 상세 judgementRequests에 표시되고 correction은 null")
    void createShowsInDetail() throws Exception {
        String id = autoPass();
        MvcResult result = request(id, "FAIL", "실물 확인 결과 고정핀이 들떠 있음", worker());

        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        JsonNode req = json(result).path("data");
        assertThat(req.path("requestId").asText()).isNotBlank();
        assertThat(req.path("inspectionId").asText()).isEqualTo(id);
        assertThat(req.path("inspectionNo").asText()).startsWith("INS-");
        assertThat(req.path("partCode").asText()).isEqualTo("DOOR");
        assertThat(req.path("originalJudgement").asText()).isEqualTo("PASS");
        assertThat(req.path("originalJudgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(req.path("currentJudgement").asText()).isEqualTo("PASS");
        assertThat(req.path("claimedJudgement").asText()).isEqualTo("FAIL");
        assertThat(req.path("area").asText()).isEqualTo("고정핀");
        assertThat(req.path("reason").asText()).isEqualTo("실물 확인 결과 고정핀이 들떠 있음");
        assertThat(req.path("requestedBy").asText()).isEqualTo("worker01");
        assertThat(req.path("requestedAt").asText()).contains("+09:00");
        assertThat(req.path("status").asText()).isEqualTo("OPEN");
        assertThat(req.path("resolvedBy").isNull()).isTrue();
        assertThat(req.path("resolvedAt").isNull()).isTrue();
        assertThat(req.path("resolveNote").isNull()).isTrue();

        JsonNode detail = detail(id);
        assertThat(detail.path("judgementRequests")).hasSize(1);
        assertThat(detail.at("/judgementRequests/0/requestId").asText()).isEqualTo(req.path("requestId").asText());
        assertThat(detail.path("correction").isNull()).isTrue();
        // 요청이 없는 검사는 빈 배열
        assertThat(detail(autoPass()).path("judgementRequests").isArray()).isTrue();
        assertThat(detail(autoPass()).path("judgementRequests")).isEmpty();
    }

    @Test
    @DisplayName("시스템 판정이 아닌 건(REVIEW 확인·확인 전)은 409 NOT_REQUESTABLE, 없는 검사는 404")
    void onlySystemJudged() throws Exception {
        MvcResult confirmed = request(reviewConfirmed(), "PASS", "사유", worker());
        assertThat(confirmed.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(confirmed)).isEqualTo("NOT_REQUESTABLE");

        ai = goodAboveThreshold();
        String pending = submitAndWait().path("inspectionId").asText();
        assertThat(errorCode(request(pending, "FAIL", "사유", worker()))).isEqualTo("NOT_REQUESTABLE");

        MvcResult missing = request(UUID.randomUUID().toString(), "FAIL", "사유", worker());
        assertThat(missing.getResponse().getStatus()).isEqualTo(404);
        assertThat(errorCode(missing)).isEqualTo("INSPECTION_NOT_FOUND");
    }

    @Test
    @DisplayName("현재 판정과 같은 요청·사유 누락·길이 초과는 400 INVALID_PARAMETER")
    void validation() throws Exception {
        String id = autoPass();
        MvcResult same = request(id, "PASS", "사유", worker());
        assertThat(same.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(same)).isEqualTo("INVALID_PARAMETER");

        assertThat(errorCode(request(id, "FAIL", " ", worker()))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(request(id, "FAIL", "가".repeat(501), worker()))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(request(id, "UNKNOWN", "사유", worker()))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(postJson("/api/v1/inspections/" + id + "/judgement-requests",
                Map.of("claimedJudgement", "FAIL", "area", "가".repeat(101), "reason", "사유"), worker())))
                .isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(postJson("/api/v1/inspections/" + id + "/judgement-requests",
                Map.of("reason", "사유"), worker()))).isEqualTo("INVALID_PARAMETER");
        // 500자·area 생략은 허용
        MvcResult ok = postJson("/api/v1/inspections/" + id + "/judgement-requests",
                Map.of("claimedJudgement", "FAIL", "reason", "가".repeat(500)), worker());
        assertThat(ok.getResponse().getStatus()).isEqualTo(201);
        assertThat(json(ok).at("/data/area").isNull()).isTrue();
    }

    @Test
    @DisplayName("대기 요청은 검사당 1건: 같은 작업자·같은 판정이면 기존 요청 200, 다른 작업자는 409 REQUEST_ALREADY_OPEN")
    void oneOpenPerInspection() throws Exception {
        String id = autoPass();
        String requestId = openRequest(id, "FAIL");

        MvcResult again = request(id, "FAIL", "다른 사유로 다시 보냄", worker());
        assertThat(again.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(again).at("/data/requestId").asText()).isEqualTo(requestId);
        assertThat(json(again).at("/data/reason").asText()).isEqualTo("실물 확인 결과 다름"); // 처음 기록 그대로

        MvcResult other = request(id, "FAIL", "사유", secondWorker());
        assertThat(other.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(other)).isEqualTo("REQUEST_ALREADY_OPEN");
        assertThat(jdbc.queryForObject("select count(*) from judgement_request where inspection_id = ?", Long.class, id))
                .isEqualTo(1);
    }

    @Test
    @DisplayName("동시 요청(같은 작업자·같은 판정): 한쪽 201, 다른 쪽 같은 요청 200, DB에는 1건")
    void createConcurrently() throws Exception {
        String id = autoPass();
        CyclicBarrier start = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        List<Integer> statuses = new ArrayList<>();
        List<String> requestIds = new ArrayList<>();
        try {
            List<Future<MvcResult>> calls = List.of("사유 A", "사유 B").stream()
                    .map(reason -> pool.submit(() -> {
                        start.await();
                        return request(id, "FAIL", reason, worker());
                    })).toList();
            for (Future<MvcResult> call : calls) {
                MvcResult result = call.get();
                statuses.add(result.getResponse().getStatus());
                requestIds.add(json(result).at("/data/requestId").asText());
            }
        } finally {
            pool.shutdown();
        }
        assertThat(statuses).containsExactlyInAnyOrder(201, 200);
        assertThat(requestIds.get(0)).isEqualTo(requestIds.get(1));
        assertThat(jdbc.queryForObject("select count(*) from judgement_request where inspection_id = ?", Long.class, id))
                .isEqualTo(1);
    }

    @Test
    @DisplayName("권한: 요청은 WORKER만, 목록·처리는 ADMIN만")
    void roles() throws Exception {
        String id = autoPass();
        assertThat(request(id, "FAIL", "사유", admin()).getResponse().getStatus()).isEqualTo(403);
        String requestId = openRequest(id, "FAIL");
        assertThat(call(get("/api/v1/admin/judgement-requests"), worker()).getResponse().getStatus()).isEqualTo(403);
        assertThat(resolve(requestId, "KEEP", "메모", worker()).getResponse().getStatus()).isEqualTo(403);
    }

    @Test
    @DisplayName("목록: 기본 OPEN 오래된 순, RESOLVED·ALL은 최근 처리·요청 순, partCode·page·size 검사")
    void list() throws Exception {
        String r1 = openRequest(autoPass(), "FAIL");
        String r2 = openRequest(autoPass(), "FAIL");
        String r3 = openRequest(autoPass(), "FAIL");
        List<String> mine = List.of(r1, r2, r3);

        assertThat(listed("", mine)).containsExactly(r1, r2, r3);
        assertThat(listed("status=OPEN&partCode=DOOR", mine)).containsExactly(r1, r2, r3);
        assertThat(listed("status=OPEN&partCode=FRAME", mine)).isEmpty();

        assertThat(resolve(r2, "KEEP", "유지", admin()).getResponse().getStatus()).isEqualTo(200);
        assertThat(resolve(r1, "CORRECT", "정정", admin()).getResponse().getStatus()).isEqualTo(200);

        assertThat(listed("status=OPEN", mine)).containsExactly(r3);
        assertThat(listed("status=RESOLVED", mine)).containsExactly(r1, r2); // 최근 처리 순
        // 처리 전이면 요청 시각으로 섞어 정렬: r3 요청 뒤에 r2·r1을 처리했으므로 r1, r2, r3
        assertThat(listed("status=ALL", mine)).containsExactly(r1, r2, r3);

        JsonNode page = json(call(get("/api/v1/admin/judgement-requests?status=ALL&page=0&size=1"), admin()))
                .path("data");
        assertThat(page.path("items")).hasSize(1);
        assertThat(page.path("size").asInt()).isEqualTo(1);
        assertThat(page.path("totalElements").asLong()).isGreaterThanOrEqualTo(3);

        MvcResult badPart = call(get("/api/v1/admin/judgement-requests?partCode=NOPE"), admin());
        assertThat(badPart.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(badPart)).isEqualTo("INVALID_PART_CODE");
        assertThat(errorCode(call(get("/api/v1/admin/judgement-requests?size=101"), admin())))
                .isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(call(get("/api/v1/admin/judgement-requests?page=-1"), admin())))
                .isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(call(get("/api/v1/admin/judgement-requests?status=KEPT"), admin())))
                .isEqualTo("INVALID_PARAMETER");
    }

    @Test
    @DisplayName("유지(KEEP): 요청 KEPT, correction 없음, 최초 판정 그대로, 처리 뒤 새 요청 가능")
    void resolveKeep() throws Exception {
        String id = autoPass();
        String requestId = openRequest(id, "FAIL");

        MvcResult result = resolve(requestId, "KEEP", "실물 다시 확인, 정상", admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        JsonNode req = json(result).at("/data/request");
        assertThat(req.path("status").asText()).isEqualTo("KEPT");
        assertThat(req.path("resolvedBy").asText()).isEqualTo("admin01");
        assertThat(req.path("resolvedAt").asText()).contains("+09:00");
        assertThat(req.path("resolveNote").asText()).isEqualTo("실물 다시 확인, 정상");
        assertThat(json(result).at("/data/correction").isNull()).isTrue();

        assertThat(inspectionRow(id)).containsEntry("final_judgement", "PASS").containsEntry("judged_by", "SYSTEM");
        assertThat(detail(id).path("correction").isNull()).isTrue();
        assertThat(historyItem(id).path("correctedJudgement").isNull()).isTrue();

        // 처리된 뒤에는 다른 작업자도 새 요청 가능 (현재 판정은 그대로 PASS)
        MvcResult next = request(id, "FAIL", "다시 요청", secondWorker());
        assertThat(next.getResponse().getStatus()).isEqualTo(201);
        assertThat(json(next).at("/data/currentJudgement").asText()).isEqualTo("PASS");
    }

    @Test
    @DisplayName("정정(CORRECT): 최초 판정은 그대로, 상세 correction·이력 correctedJudgement 표시, 다음 요청은 정정 판정 기준")
    void resolveCorrect() throws Exception {
        String id = autoPass();
        String first = openRequest(id, "FAIL");

        MvcResult result = resolve(first, "CORRECT", "실물 사진 확인, 고정핀 들뜸 맞음", admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(result).at("/data/request/status").asText()).isEqualTo("CORRECTED");
        JsonNode correction = json(result).at("/data/correction");
        assertThat(correction.path("requestId").asText()).isEqualTo(first);
        assertThat(correction.path("correctedJudgement").asText()).isEqualTo("FAIL");
        assertThat(correction.path("correctedBy").asText()).isEqualTo("admin01");
        assertThat(correction.path("correctedAt").asText()).contains("+09:00");
        assertThat(correction.path("note").asText()).isEqualTo("실물 사진 확인, 고정핀 들뜸 맞음");

        // 최초 판정(PASS·SYSTEM)은 바뀌지 않음
        assertThat(inspectionRow(id)).containsEntry("final_judgement", "PASS").containsEntry("judged_by", "SYSTEM");
        JsonNode detail = detail(id);
        assertThat(detail.at("/judgement/finalJudgement").asText()).isEqualTo("PASS");
        assertThat(detail.at("/judgement/judgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(detail.at("/correction/correctedJudgement").asText()).isEqualTo("FAIL");
        JsonNode item = historyItem(id);
        assertThat(item.path("finalJudgement").asText()).isEqualTo("PASS");
        assertThat(item.path("correctedJudgement").asText()).isEqualTo("FAIL");

        // 현재 판정이 FAIL이므로 FAIL 요청은 400, PASS 요청은 가능
        assertThat(errorCode(request(id, "FAIL", "사유", worker()))).isEqualTo("INVALID_PARAMETER");
        MvcResult back = request(id, "PASS", "재조립 후 정상", worker());
        assertThat(back.getResponse().getStatus()).isEqualTo(201);
        assertThat(json(back).at("/data/originalJudgement").asText()).isEqualTo("PASS");
        assertThat(json(back).at("/data/currentJudgement").asText()).isEqualTo("FAIL");
        String second = json(back).at("/data/requestId").asText();

        assertThat(resolve(second, "CORRECT", "정상 맞음", admin()).getResponse().getStatus()).isEqualTo(200);
        detail = detail(id);
        assertThat(detail.at("/correction/requestId").asText()).isEqualTo(second);
        assertThat(detail.at("/correction/correctedJudgement").asText()).isEqualTo("PASS");
        assertThat(detail.path("judgementRequests")).hasSize(2);
        assertThat(detail.at("/judgementRequests/0/requestId").asText()).isEqualTo(second); // 최신순
        assertThat(detail.at("/judgementRequests/1/requestId").asText()).isEqualTo(first);
        assertThat(historyItem(id).path("correctedJudgement").asText()).isEqualTo("PASS");
        assertThat(inspectionRow(id)).containsEntry("final_judgement", "PASS").containsEntry("judged_by", "SYSTEM");
    }

    @Test
    @DisplayName("이미 처리된 요청: 같은 결정이면 처음 기록 그대로 200, 다른 결정은 409, 없는 요청 404, 입력 오류 400")
    void resolveReplay() throws Exception {
        String requestId = openRequest(autoPass(), "FAIL");
        assertThat(errorCode(resolve(requestId, "UNKNOWN", "메모", admin()))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(resolve(requestId, "KEEP", " ", admin()))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(resolve(requestId, "KEEP", "가".repeat(501), admin()))).isEqualTo("INVALID_PARAMETER");

        JsonNode first = json(resolve(requestId, "KEEP", "처음 메모", admin())).at("/data/request");
        MvcResult again = resolve(requestId, "KEEP", "다른 메모", admin());
        assertThat(again.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(again).at("/data/request/resolveNote").asText()).isEqualTo("처음 메모");
        assertThat(json(again).at("/data/request/resolvedAt").asText()).isEqualTo(first.path("resolvedAt").asText());

        MvcResult other = resolve(requestId, "CORRECT", "메모", admin());
        assertThat(other.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(other)).isEqualTo("REQUEST_ALREADY_RESOLVED");

        MvcResult missing = resolve(UUID.randomUUID().toString(), "KEEP", "메모", admin());
        assertThat(missing.getResponse().getStatus()).isEqualTo(404);
        assertThat(errorCode(missing)).isEqualTo("REQUEST_NOT_FOUND");
    }

    @Test
    @DisplayName("동시 처리: 같은 결정이면 둘 다 이긴 쪽 기록 200, 다른 결정이면 200·409. DB에는 처음 기록 1건")
    void resolveConcurrently() throws Exception {
        String sameId = openRequest(autoPass(), "FAIL");
        List<MvcResult> same = concurrently(List.of(
                () -> resolve(sameId, "KEEP", "메모 A", admin()), () -> resolve(sameId, "KEEP", "메모 B", admin())));
        String winnerNote = jdbc.queryForObject("select resolve_note from judgement_request where id = ?",
                String.class, sameId);
        for (MvcResult result : same) {
            assertThat(result.getResponse().getStatus()).isEqualTo(200);
            // 진 요청도 이긴 요청의 기록을 돌려받음 (처리 전 상태가 아님)
            assertThat(json(result).at("/data/request/status").asText()).isEqualTo("KEPT");
            assertThat(json(result).at("/data/request/resolveNote").asText()).isEqualTo(winnerNote);
        }

        String diffId = openRequest(autoPass(), "FAIL");
        List<MvcResult> diff = concurrently(List.of(
                () -> resolve(diffId, "KEEP", "유지", admin()), () -> resolve(diffId, "CORRECT", "정정", admin())));
        assertThat(diff.stream().map(r -> r.getResponse().getStatus()).toList()).containsExactlyInAnyOrder(200, 409);
        assertThat(jdbc.queryForObject("select count(*) from judgement_request where id = ? and status <> 'OPEN'",
                Long.class, diffId)).isEqualTo(1);
    }

    private List<MvcResult> concurrently(List<java.util.concurrent.Callable<MvcResult>> tasks) throws Exception {
        CyclicBarrier start = new CyclicBarrier(tasks.size());
        ExecutorService pool = Executors.newFixedThreadPool(tasks.size());
        try {
            List<Future<MvcResult>> calls = tasks.stream().map(task -> pool.submit(() -> {
                start.await();
                return task.call();
            })).toList();
            List<MvcResult> results = new ArrayList<>();
            for (Future<MvcResult> call : calls) {
                results.add(call.get());
            }
            return results;
        } finally {
            pool.shutdown();
        }
    }

    // MySQL CHECK 위반(3819)은 메시지의 제약 이름으로 확인
    private void assertRejectedBy(String constraint, String sql, Object... args) {
        assertThatThrownBy(() -> jdbc.update(sql, args)).hasMessageContaining("Check constraint '" + constraint + "'");
    }

    private String userId(String loginId) {
        return jdbc.queryForObject("select id from users where login_id = ?", String.class, loginId);
    }

    private void insertRow(String inspectionId, String current, String claimed, String status, String resolvedBy,
                           String note) {
        jdbc.update("""
                insert into judgement_request (id, inspection_id, requested_by, requested_at, original_judgement,
                  current_judgement, claimed_judgement, area, reason, status, resolved_by, resolved_at, resolve_note)
                values (?, ?, ?, NOW(6), 'PASS', ?, ?, null, '사유', ?, ?, if(? is null, null, NOW(6) + interval 1 second), ?)""",
                UUID.randomUUID().toString(), inspectionId, userId("worker01"), current, claimed, status, resolvedBy,
                resolvedBy, note);
    }

    @Test
    @DisplayName("DB 제약: 값 목록, 요청 판정 ≠ 현재 판정, 상태별 처리 기록 짝, 검사당 대기 1건")
    void constraints() throws Exception {
        String id = autoPass();
        String adminId = userId("admin01");
        String insert = """
                insert into judgement_request (id, inspection_id, requested_by, requested_at, original_judgement,
                  current_judgement, claimed_judgement, reason, status, resolved_by, resolved_at, resolve_note)
                values (?, ?, ?, NOW(6), 'PASS', ?, ?, '사유', ?, ?, ?, ?)""";

        assertRejectedBy("chk_jreq_values", insert, UUID.randomUUID().toString(), id, userId("worker01"),
                "MAYBE", "FAIL", "OPEN", null, null, null);
        assertRejectedBy("chk_jreq_claim", insert, UUID.randomUUID().toString(), id, userId("worker01"),
                "PASS", "PASS", "OPEN", null, null, null);
        // OPEN인데 처리자가 있음 / 처리됐는데 메모가 없음
        assertRejectedBy("chk_jreq_resolved", insert, UUID.randomUUID().toString(), id, userId("worker01"),
                "PASS", "FAIL", "OPEN", adminId, null, null);
        assertRejectedBy("chk_jreq_resolved", insert, UUID.randomUUID().toString(), id, userId("worker01"),
                "PASS", "FAIL", "KEPT", adminId, java.time.LocalDateTime.now().plusSeconds(1), null);

        // 처리된 요청은 여러 건 가능, 대기 요청은 1건만
        insertRow(id, "PASS", "FAIL", "KEPT", adminId, "메모");
        insertRow(id, "PASS", "FAIL", "OPEN", null, null);
        assertThatThrownBy(() -> insertRow(id, "PASS", "FAIL", "OPEN", null, null))
                .hasMessageContaining("uk_judgement_request_open");
    }
}
