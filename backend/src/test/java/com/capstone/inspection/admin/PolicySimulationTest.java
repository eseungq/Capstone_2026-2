package com.capstone.inspection.admin;

import com.capstone.inspection.domain.inspection.InspectionRepository.ScoredInspection;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecheckRule;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class PolicySimulationTest {

    // 경계 0.8·0.4, 비율 100·30·10% (계약 6.11 공동시험값)
    private static final RecheckRule RULE = new RecheckRule(0.8, 0.4, 1.0, 0.3, 0.1);

    private static int seq;

    private static ScoredInspection good(double p, Judgement judgement, JudgedBy by, Judgement recheck) {
        seq++;
        return new ScoredInspection("id-" + seq, String.format("INS-%06d", seq), PredictedQuality.GOOD, p, judgement,
                by, LocalDateTime.of(2026, 11, 18, 9, 0), recheck);
    }

    private static ScoredInspection good(double p, Judgement judgement, JudgedBy by) {
        return good(p, judgement, by, null);
    }

    private static ScoredInspection rechecked(double p, Judgement recheck) {
        return good(p, Judgement.PASS, JudgedBy.SYSTEM, recheck);
    }

    private static ScoredInspection autoPass(double p) {
        return good(p, Judgement.PASS, JudgedBy.SYSTEM);
    }

    private static ScoredInspection pending(double p) {
        return good(p, null, null);
    }

    private static ScoredInspection worker(double p, Judgement judgement) {
        return good(p, judgement, JudgedBy.WORKER);
    }

    private static ScoredInspection defect(double p) {
        seq++;
        return new ScoredInspection("id-" + seq, String.format("INS-%06d", seq), PredictedQuality.DEFECT, p, null,
                null, LocalDateTime.of(2026, 11, 18, 9, 0), null);
    }

    @Test
    @DisplayName("기준 상향: 현재 기준 < p ≤ 후보만 바뀜, 작업자 판정을 라벨로 셈, DEFECT 예측은 그대로 REVIEW")
    void raise() {
        List<ScoredInspection> list = List.of(autoPass(0.01), autoPass(0.05), worker(0.06, Judgement.PASS),
                worker(0.07, Judgement.FAIL), pending(0.08), worker(0.09, Judgement.PASS), defect(0.004));

        PolicySimulation.Result r = PolicySimulation.run(list, 0.05, 0.08, RULE);

        assertThat(r.evaluatedCount()).isEqualTo(7);
        assertThat(r.defectPredictedCount()).isEqualTo(1);
        // 현재: 0.01(r 0.2 LOW 0.1) + 0.05(r 1 NEAR 1.0) → 예상 재확인 1.1, REVIEW 5와 합쳐 6.1
        assertThat(r.current()).isEqualTo(new PolicySimulation.Outcome(2, 5, 1.1, 6.1));
        // 후보 0.08: 0.01 LOW 0.1, 0.05·0.06 MID 0.3씩, 0.07·0.08 NEAR 1.0씩 → 2.7, REVIEW 2와 합쳐 4.7
        assertThat(r.candidate()).isEqualTo(new PolicySimulation.Outcome(5, 2, 2.7, 4.7));
        PolicySimulation.Change c = r.change();
        assertThat(c.direction()).isEqualTo(PolicySimulation.Direction.REVIEW_TO_AUTO_PASS);
        assertThat(c.count()).isEqualTo(3);
        assertThat(c.workerPass()).isEqualTo(1);
        assertThat(c.workerFail()).isEqualTo(1);
        assertThat(c.unverified()).isEqualTo(1);
        // 확률 높은 순: 0.08 → 0.07 → 0.06
        assertThat(c.items()).extracting(PolicySimulation.ChangedItem::calibratedDefectProbability)
                .containsExactly(0.08, 0.07, 0.06);
        assertThat(c.itemsTruncated()).isFalse();
    }

    @Test
    @DisplayName("기준 하향: 새로 REVIEW가 되는 건은 PASS·SYSTEM이라 재확인 결과가 있을 때만 라벨, 없으면 미확인")
    void lower() {
        PolicySimulation.Result r = PolicySimulation.run(List.of(autoPass(0.01), rechecked(0.04, Judgement.FAIL),
                autoPass(0.05), worker(0.06, Judgement.FAIL)), 0.05, 0.03, RULE);

        PolicySimulation.Change c = r.change();
        assertThat(c.direction()).isEqualTo(PolicySimulation.Direction.AUTO_PASS_TO_REVIEW);
        assertThat(c.count()).isEqualTo(2);
        assertThat(c.recheckFail()).isEqualTo(1);
        assertThat(c.recheckPass()).isZero();
        assertThat(c.unverified()).isEqualTo(1);
        assertThat(c.workerPass() + c.workerFail()).isZero();
        assertThat(c.items()).extracting(PolicySimulation.ChangedItem::label)
                .containsExactly(PolicySimulation.Label.UNVERIFIED, PolicySimulation.Label.RECHECK_FAIL);
        assertThat(r.candidate().autoPassCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("같은 기준치: 바뀌는 건 없음")
    void same() {
        PolicySimulation.Result r = PolicySimulation.run(List.of(autoPass(0.01), pending(0.2)), 0.05, 0.05, RULE);

        assertThat(r.change().direction()).isEqualTo(PolicySimulation.Direction.NONE);
        assertThat(r.change().count()).isZero();
        assertThat(r.current()).isEqualTo(r.candidate());
    }

    @Test
    @DisplayName("바뀌는 건이 많으면 목록은 최대 개수까지, 건수는 전체")
    void truncated() {
        List<ScoredInspection> list = new ArrayList<>();
        for (int k = 0; k < PolicySimulation.MAX_ITEMS + 5; k++) {
            list.add(pending(0.06 + k * 0.0001));
        }

        PolicySimulation.Change c = PolicySimulation.run(list, 0.05, 0.5, RULE).change();

        assertThat(c.count()).isEqualTo(PolicySimulation.MAX_ITEMS + 5);
        assertThat(c.items()).hasSize(PolicySimulation.MAX_ITEMS);
        assertThat(c.itemsTruncated()).isTrue();
    }
}
