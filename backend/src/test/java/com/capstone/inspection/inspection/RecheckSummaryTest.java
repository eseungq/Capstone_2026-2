package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository.AutoPassDecision;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshot;
import com.capstone.inspection.domain.inspection.RecheckStratum;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.RuleSummary;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse.StratumSummary;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

// 계약 6.11 요약 계산. 공동시험 설정 [합의 11/18 김도현]: 경계 0.4·0.8, 수집 100·30·10%, 가상 비교 50·30·10%
//   기준치 0.05: 보정 0.045 → NEAR(r 0.9), 0.03 → MID(r 0.6), 0.01 → LOW(r 0.2)
//   drawValue를 직접 정해 어떤 건이 뽑혔는지(실제·가상 비교)를 고정
class RecheckSummaryTest {

    private static final double THRESHOLD = 0.05;
    private static final RecheckRule TRIAL = new RecheckRule(0.8, 0.4, 1.0, 0.3, 0.1);
    private static final RecheckRule COMPARE = new RecheckRule(0.8, 0.4, 0.5, 0.3, 0.1);
    private static final LocalDateTime AT = LocalDateTime.of(2026, 11, 19, 10, 0);

    private final RecheckRuleSnapshot snapshot = new RecheckRuleSnapshot(TRIAL, "공동시험 1차");
    private final Map<String, RecheckRuleSnapshot> rules = Map.of(snapshot.getId(), snapshot);

    private static final String POLICY = "door-e02-demo-0092";
    private static final String MODEL = "door-swin-tiny-e02";
    private static final String CALIBRATOR = "door-e02-temperature-demo";

    private AutoPassDecision decided(RecheckStratum stratum, double calibrated, double draw, Judgement result) {
        return decided(POLICY, stratum, calibrated, draw, result);
    }

    private AutoPassDecision decided(String policy, RecheckStratum stratum, double calibrated, double draw,
                                     Judgement result) {
        boolean sampled = draw < TRIAL.rateOf(stratum);
        return new AutoPassDecision(UUID.randomUUID().toString(), calibrated, THRESHOLD, "DOOR", policy, MODEL,
                CALIBRATOR, snapshot.getId(),
                snapshot.getId(), sampled, stratum, draw, sampled ? result : null, AT,
                sampled && result != null ? AT.plusMinutes(5) : null, null, null);
    }

    // 결정 저장이 빠진 AUTO_PASS (판정 당시 규칙은 남음)
    private AutoPassDecision undecided(double calibrated) {
        return new AutoPassDecision(UUID.randomUUID().toString(), calibrated, THRESHOLD, "DOOR", POLICY, MODEL,
                CALIBRATOR, snapshot.getId(), null, null, null, null, null, null, null, null, null);
    }

    // NEAR 4건 모두 뽑힘(0.1 FAIL·0.3 PASS·0.6 nearAt06·0.9 FAIL), MID 10건 중 3건(모두 PASS), LOW 20건 중 2건(모두 PASS)
    private List<AutoPassDecision> trial(Judgement nearAt06) {
        List<AutoPassDecision> list = new ArrayList<>(List.of(
                decided(RecheckStratum.NEAR, 0.045, 0.1, Judgement.FAIL),
                decided(RecheckStratum.NEAR, 0.045, 0.3, Judgement.PASS),
                decided(RecheckStratum.NEAR, 0.045, 0.6, nearAt06),
                decided(RecheckStratum.NEAR, 0.045, 0.9, Judgement.FAIL)));
        for (int k = 0; k < 10; k++) {
            list.add(decided(RecheckStratum.MID, 0.03, 0.05 + 0.1 * k, Judgement.PASS)); // 0.05·0.15·0.25만 뽑힘
        }
        for (int k = 0; k < 20; k++) {
            list.add(decided(RecheckStratum.LOW, 0.01, 0.02 + 0.05 * k, Judgement.PASS)); // 0.02·0.07만 뽑힘
        }
        return list;
    }

    private RuleSummary summarize(List<AutoPassDecision> decisions) {
        RecheckSummaryResponse s = RecheckSummary.build(null, null, null, decisions, List.of(), rules, COMPARE);
        assertThat(s.rules()).hasSize(1);
        return s.rules().get(0);
    }

    @Test
    @DisplayName("모두 완료: 구간별 완료 n/m·완료율, AUTO_PASS 비중 가중 추정, 50·30·10% 가상 비교 건수가 정확하고 partial 아님")
    void allCompleted() {
        RuleSummary rule = summarize(trial(Judgement.PASS));

        assertThat(rule.ruleVersion()).isEqualTo("v1-b40-80-p100-30-10");
        assertThat(rule.trialName()).isEqualTo("공동시험 1차");
        assertThat(rule.partCode()).isEqualTo("DOOR");
        assertThat(rule.policyVersion()).isEqualTo(POLICY);
        assertThat(rule.modelVersion()).isEqualTo(MODEL);
        assertThat(rule.calibratorVersion()).isEqualTo(CALIBRATOR);
        assertThat(rule.autoPassCount()).isEqualTo(34);
        assertThat(rule.sampledCount()).isEqualTo(9);
        assertThat(rule.completionRate()).isEqualTo(1.0);
        assertThat(rule.partial()).isFalse();

        StratumSummary near = rule.strata().get(0);
        assertThat(near.stratum()).isEqualTo(RecheckStratum.NEAR);
        assertThat(near.sampledCount()).isEqualTo(4);
        assertThat(near.completedCount()).isEqualTo(4);
        assertThat(near.completionRate()).isEqualTo(1.0);
        assertThat(near.failRateAmongCompleted()).isEqualTo(0.5);
        assertThat(rule.strata().get(1).sampledCount()).isEqualTo(3);
        assertThat(rule.strata().get(2).sampledCount()).isEqualTo(2);
        // 구간 AUTO_PASS 비중 가중: NEAR 4/34 × 0.5 + MID 10/34 × 0 + LOW 20/34 × 0
        assertThat(rule.estimatedDefectRateInAutoPass()).isCloseTo(2.0 / 34, within(1e-12));

        // 가상 비교: NEAR는 draw < 0.5인 2건(0.1 FAIL·0.3 PASS)만, MID·LOW는 실제와 같은 비율이라 그대로
        RecheckSummaryResponse.Compare compare = rule.compare();
        assertThat(compare.computable()).isTrue();
        assertThat(compare.sampledCount()).isEqualTo(7);
        assertThat(compare.passCount()).isEqualTo(6);
        assertThat(compare.failCount()).isEqualTo(1);
        assertThat(compare.unverifiedCount()).isZero();
        assertThat(compare.partial()).isFalse();
        assertThat(compare.estimatedDefectRateInAutoPass()).isCloseTo(4.0 / 34 * 0.5, within(1e-12));
    }

    @Test
    @DisplayName("부분 완료: 재확인 대기·결정 누락이 남으면 추정은 나오되 partial, 완료율은 완료 ÷ 뽑힌 건")
    void partiallyCompleted() {
        List<AutoPassDecision> decisions = trial(null); // NEAR draw 0.6 건은 재확인 대기
        decisions.add(undecided(0.03));                 // MID 결정 누락

        RuleSummary rule = summarize(decisions);
        assertThat(rule.autoPassCount()).isEqualTo(35);
        assertThat(rule.undecidedCount()).isEqualTo(1);
        assertThat(rule.pendingCount()).isEqualTo(1);
        assertThat(rule.completionRate()).isCloseTo(8.0 / 9, within(1e-12));
        assertThat(rule.partial()).isTrue();

        StratumSummary near = rule.strata().get(0);
        assertThat(near.completedCount()).isEqualTo(3);
        assertThat(near.pendingCount()).isEqualTo(1);
        assertThat(near.completionRate()).isEqualTo(0.75);
        assertThat(rule.strata().get(1).undecidedCount()).isEqualTo(1);
        // 대기 건은 정상·불량으로 세지 않음: NEAR 완료 3건 중 FAIL 2 → 4/35 × 2/3
        assertThat(rule.estimatedDefectRateInAutoPass()).isCloseTo(4.0 / 35 * 2 / 3, within(1e-12));

        // 가상 비교에 들어가는 NEAR 2건은 모두 완료됐지만 결정 누락이 남아 partial
        assertThat(rule.compare().unverifiedCount()).isZero();
        assertThat(rule.compare().partial()).isTrue();
    }

    @Test
    @DisplayName("완료 0건: 뽑힌 건이 있어도 완료가 없으면 완료율 0, 추정은 비움(null), partial")
    void noneCompleted() {
        List<AutoPassDecision> decisions = List.of(
                decided(RecheckStratum.NEAR, 0.045, 0.2, null),
                decided(RecheckStratum.LOW, 0.01, 0.5, null)); // LOW 안 뽑힘
        RuleSummary rule = summarize(decisions);

        assertThat(rule.sampledCount()).isEqualTo(1);
        assertThat(rule.completionRate()).isEqualTo(0.0);
        assertThat(rule.partial()).isTrue();
        assertThat(rule.estimatedDefectRateInAutoPass()).isNull();
        assertThat(rule.strata().get(2).completionRate()).isNull(); // 뽑힌 건 없음
        assertThat(rule.compare().estimatedDefectRateInAutoPass()).isNull();
    }

    @Test
    @DisplayName("같은 추출 규칙이어도 조회 기간 중 정책이 바뀌면 항목을 나눠 불량률을 따로 계산 (섞지 않음)")
    void splitByPolicy() {
        List<AutoPassDecision> decisions = List.of(
                decided("door-e02-demo-0084", RecheckStratum.NEAR, 0.045, 0.1, Judgement.FAIL),
                decided("door-e02-demo-0092", RecheckStratum.NEAR, 0.045, 0.2, Judgement.PASS),
                decided("door-e02-demo-0092", RecheckStratum.NEAR, 0.045, 0.3, Judgement.PASS));
        List<RuleSummary> summaries = RecheckSummary.build(null, null, null, decisions, List.of(), rules, null)
                .rules();

        assertThat(summaries).extracting(RuleSummary::policyVersion)
                .containsExactly("door-e02-demo-0084", "door-e02-demo-0092");
        assertThat(summaries).extracting(RuleSummary::ruleVersion).containsOnly("v1-b40-80-p100-30-10");
        assertThat(summaries.get(0).autoPassCount()).isEqualTo(1);
        assertThat(summaries.get(0).estimatedDefectRateInAutoPass()).isEqualTo(1.0);
        assertThat(summaries.get(1).autoPassCount()).isEqualTo(2);
        assertThat(summaries.get(1).estimatedDefectRateInAutoPass()).isEqualTo(0.0);
    }
}
