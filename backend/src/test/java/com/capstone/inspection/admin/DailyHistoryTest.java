package com.capstone.inspection.admin;

import com.capstone.inspection.admin.DailyHistory.RequestSummary;
import com.capstone.inspection.admin.dto.DailyDetailResponse.Band;
import com.capstone.inspection.admin.dto.DailyHistoryRow;
import com.capstone.inspection.domain.inspection.InspectionRepository.DailyInspection;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.JudgementRequestRepository.RequestFact;
import com.capstone.inspection.domain.inspection.JudgementRequestStatus;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

// 날짜별 이력 집계·기준 구간 (DB 없이)
class DailyHistoryTest {

    private static final LocalDateTime AT = LocalDateTime.of(2025, 1, 10, 12, 0);

    private static DailyInspection autoPass(String id) {
        return new DailyInspection(id, "INS-" + id, AT, InspectionStatus.COMPLETED, InspectionSource.DEVICE,
                RecommendedAction.AUTO_PASS, PredictedQuality.GOOD, 0.01, Judgement.PASS, null, "m", "c");
    }

    private static DailyInspection review(String id, PredictedQuality quality, double p, Judgement judgement) {
        return new DailyInspection(id, "INS-" + id, AT, InspectionStatus.COMPLETED, InspectionSource.DEVICE,
                RecommendedAction.REVIEW, quality, p, judgement, null, "m", "c");
    }

    private static RequestFact fact(String inspectionId, String requestId, JudgementRequestStatus status,
                                    Judgement claimed, int minute) {
        return new RequestFact(inspectionId, requestId, status, claimed,
                status == JudgementRequestStatus.OPEN ? null : AT.plusMinutes(minute));
    }

    @Test
    @DisplayName("마지막 정정이 원래 판정으로 되돌리면 자동 통과 후 불량으로 세지 않음, 처리된 요청은 검사당 1건")
    void latestCorrectionDecides() {
        Map<String, RequestSummary> requests = DailyHistory.summarize(List.of(
                fact("a", "r1", JudgementRequestStatus.CORRECTED, Judgement.FAIL, 1),
                fact("a", "r2", JudgementRequestStatus.CORRECTED, Judgement.PASS, 2),
                fact("b", "r3", JudgementRequestStatus.CORRECTED, Judgement.FAIL, 1),
                fact("b", "r4", JudgementRequestStatus.KEPT, Judgement.PASS, 3),
                fact("c", "r5", JudgementRequestStatus.OPEN, Judgement.FAIL, 0)));

        List<DailyHistoryRow> rows = DailyHistory.rows(List.of(autoPass("a"), autoPass("b"), autoPass("c")),
                Map.of(), requests);

        assertThat(rows).hasSize(1);
        DailyHistoryRow row = rows.get(0);
        assertThat(row.confirmedOpposite().autoPassThenFail()).isEqualTo(1);
        assertThat(row.confirmedOpposite().resolvedRequests()).isEqualTo(2);
        assertThat(row.openRequests()).isEqualTo(1);
        assertThat(row.total()).isEqualTo(3);
        assertThat(row.policyVersion()).isNull();
        assertThat(row.autoFailEnabled()).isFalse();
    }

    @Test
    @DisplayName("구간 경계: 통과 구간은 기준 초과~기준+band 이하, 불량 구간은 기준−band 이상~기준 미만")
    void bandBoundaries() {
        List<DailyInspection> items = List.of(
                review("p1", PredictedQuality.GOOD, 0.03, null),
                review("p2", PredictedQuality.GOOD, 0.08, Judgement.PASS),
                review("p3", PredictedQuality.GOOD, 0.080001, null),
                review("f1", PredictedQuality.DEFECT, 0.75, Judgement.FAIL),
                review("f2", PredictedQuality.DEFECT, 0.8, null),
                review("f3", PredictedQuality.DEFECT, 0.749999, null));

        Band pass = DailyBands.passBand(items, 0.03, 0.05, Map.of());
        Band fail = DailyBands.failBand(items, 0.8, 0.05, Map.of());

        assertThat(pass.items()).extracting(i -> i.inspectionId()).containsExactly("p2");
        assertThat(List.of(pass.from(), pass.to(), (double) pass.pass())).containsExactly(0.03, 0.08, 1.0);
        assertThat(fail.items()).extracting(i -> i.inspectionId()).containsExactly("f1");
        assertThat(List.of(fail.from(), fail.to(), (double) fail.fail())).containsExactly(0.75, 0.8, 1.0);
    }
}
