package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.user.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.Optional;

public interface AutoPassRecheckRepository extends JpaRepository<AutoPassRecheck, String> {

    boolean existsByInspectionId(String inspectionId);

    @Query("select r from AutoPassRecheck r left join fetch r.recheckedBy where r.inspection.id = :inspectionId")
    Optional<AutoPassRecheck> findByInspectionIdWithUser(String inspectionId);

    // 재확인 목록 (계약 6.11). done=false면 대기, true면 완료. 뽑힌 순서
    @Query(value = """
            select r from AutoPassRecheck r join fetch r.inspection i join fetch i.part p left join fetch r.recheckedBy
            where ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)
            order by r.sampledAt, r.id""",
            countQuery = """
            select count(r) from AutoPassRecheck r join r.inspection i join i.part p
            where ((:done = false and r.result is null) or (:done = true and r.result is not null))
              and (:partCode is null or p.partCode = :partCode)""")
    Page<AutoPassRecheck> search(boolean done, String partCode, Pageable pageable);

    // 재확인 결과 기록. 아직 결과가 없을 때만 갱신되므로 동시 제출 중 1건만 1을 받음
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update AutoPassRecheck r set r.result = :result, r.comment = :comment,
                   r.recheckedBy = :user, r.recheckedAt = :at
            where r.inspection.id = :inspectionId and r.result is null""")
    int markResult(String inspectionId, Judgement result, String comment, User user, LocalDateTime at);
}
