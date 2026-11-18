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
            select r from AutoPassRecheck r left join fetch r.recheckedBy
            where r.inspection.id = :inspectionId and r.sampled = true""")
    Optional<AutoPassRecheck> findSampledByInspectionIdWithUser(String inspectionId);

    // 추출 결정이 없는 AUTO_PASS (결정 저장 실패·결정 전). completedAt 기준 [from, to), 오래된 순
    //   보정 확률·기준치가 없는 건은 결정할 수 없어 제외 (계속 다시 시도하지 않도록)
    @Query("""
            select i.id from Inspection i
            where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED
              and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.AUTO_PASS
              and i.judgedBy = com.capstone.inspection.domain.inspection.JudgedBy.SYSTEM
              and i.calibratedDefectProbability is not null and i.passThresholdApplied is not null
              and i.completedAt >= :from and i.completedAt < :to
              and not exists (select 1 from AutoPassRecheck r where r.inspection = i)
            order by i.completedAt, i.id""")
    List<String> findUndecidedAutoPass(LocalDateTime from, LocalDateTime to, Pageable pageable);

    // 재확인 목록 (계약 6.11). 뽑힌 건 중 done=false면 대기, true면 완료. 뽑힌 순서
    @Query(value = """
            select r from AutoPassRecheck r join fetch r.inspection i join fetch i.part p left join fetch r.recheckedBy
            where r.sampled = true
              and ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)
            order by r.sampledAt, r.id""",
            countQuery = """
            select count(r) from AutoPassRecheck r join r.inspection i join i.part p
            where r.sampled = true
              and ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)""")
    Page<AutoPassRecheck> search(boolean done, String partCode, Pageable pageable);

    // 재확인 결과 기록. 뽑힌 건에 아직 결과가 없을 때만 갱신되므로 동시 제출 중 1건만 1을 받음
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update AutoPassRecheck r set r.result = :result, r.comment = :comment,
                   r.recheckedBy = :user, r.recheckedAt = :at
            where r.inspection.id = :inspectionId and r.sampled = true and r.result is null""")
    int markResult(String inspectionId, Judgement result, String comment, User user, LocalDateTime at);
}
