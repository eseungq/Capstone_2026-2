package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.DailyHistoryRow;
import com.capstone.inspection.admin.dto.DailyHistoryRow.ConfirmedOpposite;
import com.capstone.inspection.admin.dto.DailyHistoryRow.Progress;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.InspectionRepository.DailyInspection;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.JudgementRequestRepository.RequestFact;
import com.capstone.inspection.domain.inspection.JudgementRequestStatus;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.model.AutomationPolicy;

import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

// 날짜별 이력 집계 (계약 6.13). DB 조회 없이 읽어 온 값만으로 계산
//   행 = (KST 날짜, 정책, 모델, 보정기). 정책 없는 건은 정책 null 행으로 모이며,
//   정책 없음 REVIEW(보정기 있음)와 수동 전환·분석 실패(보정기 없음)는 보정기 값이 달라 보통 다른 행이 됨
final class DailyHistory {

    // 검사별 판정 확인 요청 요약. corrected = 마지막 CORRECTED 요청의 판정 (JudgementCorrections와 같은 순서)
    record RequestSummary(boolean open, boolean resolved, Judgement corrected) {
        static final RequestSummary NONE = new RequestSummary(false, false, null);
    }

    private record GroupKey(LocalDate date, String policyId, String modelVersion, String calibratorVersion) {
    }

    private static final Comparator<RequestFact> LATEST_RESOLVED =
            Comparator.comparing(RequestFact::resolvedAt).thenComparing(RequestFact::requestId);

    // 최신 날짜부터, 날짜 안에서는 정책 버전·모델·보정기 순 (정책 없는 행은 뒤)
    private static final Comparator<DailyHistoryRow> ROW_ORDER = Comparator
            .comparing(DailyHistoryRow::date, Comparator.reverseOrder())
            .thenComparing(DailyHistoryRow::policyVersion, Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(DailyHistoryRow::modelVersion, Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(DailyHistoryRow::calibratorVersion, Comparator.nullsLast(Comparator.naturalOrder()));

    private DailyHistory() {
    }

    static List<DailyHistoryRow> rows(List<DailyInspection> inspections, Map<String, AutomationPolicy> policies,
                                      Map<String, RequestSummary> requests) {
        Map<GroupKey, List<DailyInspection>> groups = inspections.stream()
                .collect(Collectors.groupingBy(DailyHistory::keyOf));
        return groups.entrySet().stream()
                .map(e -> row(e.getKey(), e.getValue(), policyOf(policies, e.getKey().policyId()), requests))
                .sorted(ROW_ORDER)
                .toList();
    }

    // 불변 Map은 null 키 조회를 막으므로 정책 없는 행은 먼저 거름
    private static AutomationPolicy policyOf(Map<String, AutomationPolicy> policies, String policyId) {
        return policyId == null ? null : policies.get(policyId);
    }

    static Map<String, RequestSummary> summarize(List<RequestFact> facts) {
        return facts.stream().collect(Collectors.groupingBy(RequestFact::inspectionId)).entrySet().stream()
                .collect(Collectors.toUnmodifiableMap(Map.Entry::getKey, e -> summaryOf(e.getValue())));
    }

    private static RequestSummary summaryOf(List<RequestFact> facts) {
        boolean open = facts.stream().anyMatch(f -> f.status() == JudgementRequestStatus.OPEN);
        boolean resolved = facts.stream().anyMatch(f -> f.status() != JudgementRequestStatus.OPEN);
        Judgement corrected = facts.stream().filter(f -> f.status() == JudgementRequestStatus.CORRECTED)
                .max(LATEST_RESOLVED).map(RequestFact::claimedJudgement).orElse(null);
        return new RequestSummary(open, resolved, corrected);
    }

    private static GroupKey keyOf(DailyInspection i) {
        return new GroupKey(Times.kstDate(i.receivedAt()), i.policyId(), i.modelVersion(), i.calibratorVersion());
    }

    private static DailyHistoryRow row(GroupKey key, List<DailyInspection> items, AutomationPolicy policy,
                                       Map<String, RequestSummary> requests) {
        int autoPass = count(items, i -> isAction(i, RecommendedAction.AUTO_PASS));
        int autoFail = count(items, i -> isAction(i, RecommendedAction.AUTO_FAIL));
        Progress review = progress(items, i -> isReview(i) && i.source() != InspectionSource.MANUAL);
        Progress manual = progress(items, i -> isReview(i) && i.source() == InspectionSource.MANUAL);
        int failed = count(items, i -> i.status() == InspectionStatus.FAILED);
        ConfirmedOpposite opposite = new ConfirmedOpposite(
                count(items, i -> isAction(i, RecommendedAction.AUTO_PASS)
                        && summary(requests, i).corrected() == Judgement.FAIL),
                count(items, i -> isAction(i, RecommendedAction.AUTO_FAIL)
                        && summary(requests, i).corrected() == Judgement.PASS),
                count(items, i -> summary(requests, i).resolved()));
        int open = count(items, i -> summary(requests, i).open());
        return new DailyHistoryRow(key.date(), key.policyId(),
                policy != null ? policy.getPolicyVersion() : null, key.modelVersion(), key.calibratorVersion(),
                policy != null ? policy.getPassThreshold() : null, policy != null ? policy.getFailThreshold() : null,
                policy != null && policy.isAutoFailEnabled(),
                autoPass + autoFail + review.total(), autoPass, autoFail, review, manual, failed, opposite, open);
    }

    static boolean isReview(DailyInspection i) {
        return isAction(i, RecommendedAction.REVIEW);
    }

    private static boolean isAction(DailyInspection i, RecommendedAction action) {
        return i.status() == InspectionStatus.COMPLETED && i.recommendedAction() == action;
    }

    static RequestSummary summary(Map<String, RequestSummary> requests, DailyInspection i) {
        return requests.getOrDefault(i.id(), RequestSummary.NONE);
    }

    private static Progress progress(List<DailyInspection> items, Predicate<DailyInspection> assigned) {
        List<DailyInspection> matched = items.stream().filter(assigned).toList();
        return new Progress(count(matched, i -> i.finalJudgement() != null), matched.size());
    }

    private static int count(List<DailyInspection> items, Predicate<DailyInspection> predicate) {
        return (int) items.stream().filter(predicate).count();
    }
}
