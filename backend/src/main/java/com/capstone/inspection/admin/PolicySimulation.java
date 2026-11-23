package com.capstone.inspection.admin;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.InspectionRepository.ScoredInspection;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.inspection.RecheckRules;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

// 같은 검사들에 현재 기준치와 후보 기준치를 대입해 판정이 바뀌는 건을 셈 (계약 6.9.1)
//   판정 규칙은 PolicyEvaluator와 같음: DEFECT 예측은 기준치와 무관하게 REVIEW, GOOD은 보정 확률 ≤ 기준치면 AUTO_PASS
//   실제 라벨은 작업자 판정, 그다음 AUTO_PASS 표본 재확인 결과(6.11). PASS·SYSTEM만 있는 건은 미확인으로 셈
//   예상 재확인 건수: 그 기준치로 AUTO_PASS가 되는 건마다 현재 재확인 규칙의 구간 비율을 더한 값 (기대값)
public final class PolicySimulation {

    static final int MAX_ITEMS = 100;

    public enum Direction { NONE, REVIEW_TO_AUTO_PASS, AUTO_PASS_TO_REVIEW }

    public enum Label { WORKER_PASS, WORKER_FAIL, RECHECK_PASS, RECHECK_FAIL, UNVERIFIED }

    // expectedCheckCount = reviewCount + expectedRecheckCount (REVIEW 확인과 재확인을 합친 예상 확인 건수)
    public record Outcome(long autoPassCount, long reviewCount, double expectedRecheckCount,
                          double expectedCheckCount) {

        static Outcome of(long total, long autoPass, double expectedRecheck) {
            long review = total - autoPass;
            return new Outcome(autoPass, review, round1(expectedRecheck), round1(review + expectedRecheck));
        }
    }

    public record ChangedItem(String inspectionId, String inspectionNo, double calibratedDefectProbability, Label label,
                              OffsetDateTime receivedAt) {
    }

    public record Change(Direction direction, long count, long workerPass, long workerFail, long recheckPass,
                         long recheckFail, long unverified, List<ChangedItem> items, boolean itemsTruncated) {
    }

    public record Result(long evaluatedCount, long defectPredictedCount, Outcome current, Outcome candidate, Change change) {
    }

    private PolicySimulation() {
    }

    static Result run(List<ScoredInspection> inspections, double currentThreshold, double candidateThreshold,
                      RecheckRule recheckRule) {
        Direction direction = candidateThreshold > currentThreshold ? Direction.REVIEW_TO_AUTO_PASS
                : candidateThreshold < currentThreshold ? Direction.AUTO_PASS_TO_REVIEW : Direction.NONE;
        long defectPredicted = 0;
        long currentAuto = 0;
        long candidateAuto = 0;
        long workerPass = 0;
        long workerFail = 0;
        long recheckPass = 0;
        long recheckFail = 0;
        long unverified = 0;
        double currentRecheck = 0;
        double candidateRecheck = 0;
        List<ChangedItem> changed = new ArrayList<>();
        for (ScoredInspection i : inspections) {
            if (i.predictedQuality() == PredictedQuality.DEFECT) {
                defectPredicted++;
                continue;
            }
            Double p = i.calibratedDefectProbability();
            boolean nowAuto = p != null && p <= currentThreshold;
            boolean candAuto = p != null && p <= candidateThreshold;
            currentAuto += nowAuto ? 1 : 0;
            candidateAuto += candAuto ? 1 : 0;
            currentRecheck += nowAuto ? expectedRate(p, currentThreshold, recheckRule) : 0;
            candidateRecheck += candAuto ? expectedRate(p, candidateThreshold, recheckRule) : 0;
            if (nowAuto == candAuto) {
                continue;
            }
            Label label = labelOf(i);
            switch (label) {
                case WORKER_PASS -> workerPass++;
                case WORKER_FAIL -> workerFail++;
                case RECHECK_PASS -> recheckPass++;
                case RECHECK_FAIL -> recheckFail++;
                case UNVERIFIED -> unverified++;
            }
            changed.add(new ChangedItem(i.id(), i.inspectionNo(), p, label, Times.toOffset(i.receivedAt())));
        }
        // 보정 확률이 높은 건(불량일 가능성이 큰 건)부터 사진을 보도록
        changed.sort(Comparator.comparingDouble(ChangedItem::calibratedDefectProbability).reversed()
                .thenComparing(ChangedItem::inspectionNo));
        long total = inspections.size();
        boolean truncated = changed.size() > MAX_ITEMS;
        Change change = new Change(direction, changed.size(), workerPass, workerFail, recheckPass, recheckFail,
                unverified, List.copyOf(truncated ? changed.subList(0, MAX_ITEMS) : changed), truncated);
        return new Result(total, defectPredicted, Outcome.of(total, currentAuto, currentRecheck),
                Outcome.of(total, candidateAuto, candidateRecheck), change);
    }

    // AUTO_PASS 1건이 재확인으로 뽑힐 확률 (그 기준치에서의 구간 비율)
    private static double expectedRate(double calibrated, double threshold, RecheckRule rule) {
        return rule.rateOf(RecheckRules.stratum(calibrated, threshold, rule));
    }

    private static Label labelOf(ScoredInspection i) {
        if (i.judgedBy() == JudgedBy.WORKER && i.finalJudgement() != null) {
            return i.finalJudgement() == Judgement.FAIL ? Label.WORKER_FAIL : Label.WORKER_PASS;
        }
        if (i.recheckResult() != null) {
            return i.recheckResult() == Judgement.FAIL ? Label.RECHECK_FAIL : Label.RECHECK_PASS;
        }
        return Label.UNVERIFIED;
    }

    private static double round1(double value) {
        return Math.round(value * 10) / 10.0;
    }
}
