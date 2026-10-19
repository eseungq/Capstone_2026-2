package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.criteria.Subquery;
import org.springframework.data.jpa.domain.Specification;

import java.time.LocalDateTime;

// 검사 목록 조회 조건 (이력·확인 필요 목록·모니터링 공통)
public final class InspectionSpecs {

    private InspectionSpecs() {
    }

    // 부품을 함께 조회 (목록의 partCode용 N+1 방지). count 쿼리에는 fetch를 붙이지 않음
    public static Specification<Inspection> fetchPart() {
        return (root, query, cb) -> {
            if (query != null && query.getResultType() != Long.class && query.getResultType() != long.class) {
                root.fetch("part");
            }
            return null;
        };
    }

    public static Specification<Inspection> partId(String partId) {
        return (root, query, cb) -> cb.equal(root.get("part").get("id"), partId);
    }

    // receivedAt ≥ from
    public static Specification<Inspection> receivedFrom(LocalDateTime from) {
        return (root, query, cb) -> cb.greaterThanOrEqualTo(root.get("receivedAt"), from);
    }

    // receivedAt < to
    public static Specification<Inspection> receivedBefore(LocalDateTime to) {
        return (root, query, cb) -> cb.lessThan(root.get("receivedAt"), to);
    }

    // displayState → status·recommendedAction·finalJudgement 조합 (DisplayState.of와 같은 규칙)
    public static Specification<Inspection> displayState(DisplayState state) {
        return (root, query, cb) -> displayStatePredicate(root, cb, state);
    }

    // 확인 필요 목록 대상: REVIEW_PENDING
    public static Specification<Inspection> reviewPending() {
        return displayState(DisplayState.REVIEW_PENDING);
    }

    // 확인 필요 목록 대상: 아직 재검사하지 않은 FAILED
    public static Specification<Inspection> failedNotRetried() {
        return (root, query, cb) -> {
            Subquery<String> retried = query.subquery(String.class);
            Root<Inspection> r = retried.from(Inspection.class);
            retried.select(r.get("id")).where(cb.equal(r.get("retryOfInspectionId"), root.get("id")));
            return cb.and(cb.equal(root.get("status"), InspectionStatus.FAILED), cb.not(cb.exists(retried)));
        };
    }

    // 커서 이후 (receivedAt, id) 오름차순
    public static Specification<Inspection> after(LocalDateTime receivedAt, String id) {
        return (root, query, cb) -> cb.or(
                cb.greaterThan(root.get("receivedAt"), receivedAt),
                cb.and(cb.equal(root.get("receivedAt"), receivedAt), cb.greaterThan(root.get("id"), id)));
    }

    private static Predicate displayStatePredicate(Root<Inspection> root, CriteriaBuilder cb, DisplayState state) {
        var status = root.<InspectionStatus>get("status");
        var action = root.<RecommendedAction>get("recommendedAction");
        var judgement = root.get("finalJudgement");
        return switch (state) {
            case ANALYZING -> status.in(InspectionStatus.RECEIVED, InspectionStatus.ANALYZING);
            case AUTO_PASS -> cb.and(cb.equal(status, InspectionStatus.COMPLETED),
                    cb.equal(action, RecommendedAction.AUTO_PASS));
            case REVIEW_PENDING -> cb.and(cb.equal(status, InspectionStatus.COMPLETED),
                    cb.equal(action, RecommendedAction.REVIEW), cb.isNull(judgement));
            case REVIEW_DONE -> cb.and(cb.equal(status, InspectionStatus.COMPLETED),
                    cb.equal(action, RecommendedAction.REVIEW), cb.isNotNull(judgement));
            case FAILED -> cb.equal(status, InspectionStatus.FAILED);
        };
    }
}
