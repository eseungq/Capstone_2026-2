package com.capstone.inspection.admin;

import com.capstone.inspection.admin.DailyHistory.RequestSummary;
import com.capstone.inspection.admin.dto.DailyDetailResponse.Band;
import com.capstone.inspection.admin.dto.DailyDetailResponse.Item;
import com.capstone.inspection.domain.inspection.InspectionRepository.DailyInspection;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

// 기준 상세의 두 구간 (계약 6.13). 기준 ± band 경계는 BigDecimal로 계산해 0.03 + 0.05 같은 합의 오차를 피함
//   통과 기준 위: GOOD 예측 REVIEW, passThreshold < p ≤ passThreshold + band
//   불량 기준 아래: DEFECT 예측 REVIEW, failThreshold − band ≤ p < failThreshold
//   수동 전환 REVIEW는 확률이 없어 자연히 빠지지만 조건으로도 뺌
final class DailyBands {

    private static final Comparator<Item> BY_PROBABILITY = Comparator
            .comparing(Item::calibratedDefectProbability).thenComparing(Item::inspectionNo);

    private DailyBands() {
    }

    static Band passBand(List<DailyInspection> inspections, double passThreshold, double band,
                         Map<String, RequestSummary> requests) {
        BigDecimal from = decimal(passThreshold);
        BigDecimal to = from.add(decimal(band));
        return collect(inspections, PredictedQuality.GOOD, from, to, false, requests);
    }

    static Band failBand(List<DailyInspection> inspections, double failThreshold, double band,
                         Map<String, RequestSummary> requests) {
        BigDecimal to = decimal(failThreshold);
        BigDecimal from = to.subtract(decimal(band));
        return collect(inspections, PredictedQuality.DEFECT, from, to, true, requests);
    }

    // lowerInclusive = true면 [from, to), false면 (from, to]
    private static Band collect(List<DailyInspection> inspections, PredictedQuality quality, BigDecimal from,
                                BigDecimal to, boolean lowerInclusive, Map<String, RequestSummary> requests) {
        List<Item> items = inspections.stream()
                .filter(i -> DailyHistory.isReview(i) && i.source() != InspectionSource.MANUAL)
                .filter(i -> i.predictedQuality() == quality && i.calibratedDefectProbability() != null)
                .filter(i -> within(decimal(i.calibratedDefectProbability()), from, to, lowerInclusive))
                .map(i -> new Item(i.id(), i.inspectionNo(), i.calibratedDefectProbability(), i.finalJudgement(),
                        DailyHistory.summary(requests, i).corrected()))
                .sorted(BY_PROBABILITY)
                .toList();
        int pass = countJudgement(items, Judgement.PASS);
        int fail = countJudgement(items, Judgement.FAIL);
        return new Band(from.doubleValue(), to.doubleValue(), items.size(), pass, fail,
                items.size() - pass - fail, items);
    }

    private static boolean within(BigDecimal p, BigDecimal from, BigDecimal to, boolean lowerInclusive) {
        return lowerInclusive
                ? p.compareTo(from) >= 0 && p.compareTo(to) < 0
                : p.compareTo(from) > 0 && p.compareTo(to) <= 0;
    }

    private static int countJudgement(List<Item> items, Judgement judgement) {
        return (int) items.stream().filter(i -> i.finalJudgement() == judgement).count();
    }

    private static BigDecimal decimal(double value) {
        return BigDecimal.valueOf(value);
    }
}
