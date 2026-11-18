package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.user.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface AutoPassRecheckRepository extends JpaRepository<AutoPassRecheck, String> {

    // 추출 결정이 이미 있는지 (뽑힘·안 뽑힘 모두)
    boolean existsByInspectionId(String inspectionId);

    // 재확인 대상으로 뽑힌 건만. 뽑히지 않은 결정은 상세·재확인에서 표본이 아닌 것과 같음
    @Query("""
            select r from AutoPassRecheck r left join fetch r.recheckedBy left join fetch r.acknowledgedBy
              left join fetch r.rule
            where r.inspection.id = :inspectionId and r.sampled = true""")
    Optional<AutoPassRecheck> findSampledByInspectionIdWithUser(String inspectionId);

    // 추출 결정이 없는 AUTO_PASS (결정 저장 실패·결정 전). completedAt 기준 [from, to), 오래된 순
    //   판정 당시 규칙(recheckRule)이 없거나 보정 확률·기준치가 없는 건은 결정할 수 없어 제외
    @Query("""
            select i.id from Inspection i
            where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED
              and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.AUTO_PASS
              and i.judgedBy = com.capstone.inspection.domain.inspection.JudgedBy.SYSTEM
              and i.calibratedDefectProbability is not null and i.passThresholdApplied is not null
              and i.recheckRule is not null
              and i.completedAt >= :from and i.completedAt < :to
              and not exists (select 1 from AutoPassRecheck r where r.inspection = i)
            order by i.completedAt, i.id""")
    List<String> findUndecidedAutoPass(LocalDateTime from, LocalDateTime to, Pageable pageable);

    // 재확인 목록 (계약 6.11). 뽑힌 건 중 done=false면 대기, true면 완료. 뽑힌 순서
    //   result·acknowledged는 완료(done=true)에서만 의미 있음 (서비스가 확인). null이면 거르지 않음
    @Query(value = """
            select r from AutoPassRecheck r join fetch r.inspection i join fetch i.part p
              left join fetch r.recheckedBy left join fetch r.acknowledgedBy
            where r.sampled = true
              and ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)
              and (:result is null or r.result = :result)
              and (:acknowledged is null or (:acknowledged = true and r.acknowledgedAt is not null)
                   or (:acknowledged = false and r.acknowledgedAt is null))
            order by r.sampledAt, r.id""",
            countQuery = """
            select count(r) from AutoPassRecheck r join r.inspection i join i.part p
            where r.sampled = true
              and ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)
              and (:result is null or r.result = :result)
              and (:acknowledged is null or (:acknowledged = true and r.acknowledgedAt is not null)
                   or (:acknowledged = false and r.acknowledgedAt is null))""")
    Page<AutoPassRecheck> search(boolean done, String partCode, Judgement result, Boolean acknowledged,
                                 Pageable pageable);

    // 재확인 결과 기록. 뽑힌 건에 아직 결과가 없을 때만 갱신되므로 동시 제출 중 1건만 1을 받음
    //   화면 체류 시간 3개는 선택 (셋 다 null이거나 셋 다 값, 서비스가 확인)
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update AutoPassRecheck r set r.result = :result, r.comment = :comment,
                   r.recheckedBy = :user, r.recheckedAt = :at,
                   r.screenTiming.screenDwellMs = :dwellMs, r.screenTiming.firstOpenedAt = :firstOpenedAt,
                   r.screenTiming.openCount = :openCount
            where r.inspection.id = :inspectionId and r.sampled = true and r.result is null""")
    int markResult(String inspectionId, Judgement result, String comment, User user, LocalDateTime at,
                   Long dwellMs, LocalDateTime firstOpenedAt, Integer openCount);

    // 관리자 확인함 (계약 6.11). 재확인 FAIL이고 아직 확인 전일 때만 갱신 → 동시 요청 중 1건만 1을 받음
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update AutoPassRecheck r set r.acknowledgedBy = :user, r.acknowledgedAt = :at, r.acknowledgeNote = :note
            where r.inspection.id = :inspectionId and r.sampled = true
              and r.result = com.capstone.inspection.domain.inspection.Judgement.FAIL and r.acknowledgedAt is null""")
    int markAcknowledged(String inspectionId, User user, LocalDateTime at, String note);

    // 요약용 (계약 6.11): 기간 안의 AUTO_PASS와 그 결정 행 (없으면 결정 관련 값 null). receivedAt 기준 [from, to)
    //   규칙은 결정 행의 규칙, 결정 전이면 판정 당시 검사에 남긴 규칙 (둘 다 없으면 null: 기능 꺼짐·V8 기록)
    record AutoPassDecision(String inspectionId, double calibrated, double threshold,
                            String inspectionRuleId, String decisionRuleId,
                            Boolean sampled, RecheckStratum stratum, Double drawValue, Judgement result,
                            LocalDateTime sampledAt, LocalDateTime recheckedAt, Long screenDwellMs, Integer openCount) {
    }

    @Query("""
            select new com.capstone.inspection.domain.inspection.AutoPassRecheckRepository$AutoPassDecision(
                   i.id, i.calibratedDefectProbability, i.passThresholdApplied, ir.id, rr.id,
                   r.sampled, r.stratum, r.drawValue, r.result, r.sampledAt, r.recheckedAt,
                   r.screenTiming.screenDwellMs, r.screenTiming.openCount)
            from Inspection i join i.part p left join i.recheckRule ir
              left join AutoPassRecheck r on r.inspection = i left join r.rule rr
            where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED
              and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.AUTO_PASS
              and i.judgedBy = com.capstone.inspection.domain.inspection.JudgedBy.SYSTEM
              and i.calibratedDefectProbability is not null and i.passThresholdApplied is not null
              and (:partCode is null or p.partCode = :partCode)
              and (:from is null or i.receivedAt >= :from) and (:to is null or i.receivedAt < :to)""")
    List<AutoPassDecision> findAutoPassDecisions(String partCode, LocalDateTime from, LocalDateTime to);

    // 요약용: 기간 안의 REVIEW 건의 완료 시각과 작업자 확인 (확인 전이면 confirmedAt null)
    record ReviewTiming(LocalDateTime completedAt, LocalDateTime confirmedAt, Long screenDwellMs,
                        Integer openCount) {
    }

    @Query("""
            select new com.capstone.inspection.domain.inspection.AutoPassRecheckRepository$ReviewTiming(
                   i.completedAt, c.confirmedAt, c.screenTiming.screenDwellMs, c.screenTiming.openCount)
            from Inspection i join i.part p left join WorkerConfirmation c on c.inspection = i
            where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED
              and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.REVIEW
              and (:partCode is null or p.partCode = :partCode)
              and (:from is null or i.receivedAt >= :from) and (:to is null or i.receivedAt < :to)""")
    List<ReviewTiming> findReviewTimings(String partCode, LocalDateTime from, LocalDateTime to);
}
