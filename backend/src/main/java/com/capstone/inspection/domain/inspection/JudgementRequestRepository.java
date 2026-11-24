package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.user.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface JudgementRequestRepository extends JpaRepository<JudgementRequest, String> {

    // 응답에 필요한 검사·부품·요청자·처리자를 함께 읽음
    @Query("""
            select r from JudgementRequest r join fetch r.inspection i join fetch i.part
              join fetch r.requestedBy left join fetch r.resolvedBy
            where r.id = :id""")
    Optional<JudgementRequest> findWithDetailsById(String id);

    // 검사의 처리 대기 요청 (검사당 최대 1건, V12 open_key)
    @Query("""
            select r from JudgementRequest r join fetch r.inspection i join fetch i.part
              join fetch r.requestedBy left join fetch r.resolvedBy
            where i.id = :inspectionId
              and r.status = com.capstone.inspection.domain.inspection.JudgementRequestStatus.OPEN""")
    Optional<JudgementRequest> findOpenByInspectionId(String inspectionId);

    // 상세용: 검사의 요청 전체, 최신순
    @Query("""
            select r from JudgementRequest r join fetch r.inspection i join fetch i.part
              join fetch r.requestedBy left join fetch r.resolvedBy
            where i.id = :inspectionId
            order by r.requestedAt desc, r.id desc""")
    List<JudgementRequest> findByInspectionIdLatestFirst(String inspectionId);

    // 이력·현재 판정용: 검사들의 CORRECTED 요청 (검사별 마지막 정정은 JudgementCorrections가 고름)
    @Query("""
            select r from JudgementRequest r left join fetch r.resolvedBy
            where r.inspection.id in :inspectionIds
              and r.status = com.capstone.inspection.domain.inspection.JudgementRequestStatus.CORRECTED""")
    List<JudgementRequest> findCorrectedByInspectionIds(Collection<String> inspectionIds);

    // 관리자 목록: 대기 요청, 오래된 요청부터
    @Query(value = """
            select r from JudgementRequest r join fetch r.inspection i join fetch i.part p
              join fetch r.requestedBy
            where r.status = com.capstone.inspection.domain.inspection.JudgementRequestStatus.OPEN
              and (:partCode is null or p.partCode = :partCode)
            order by r.requestedAt, r.id""",
            countQuery = """
            select count(r) from JudgementRequest r join r.inspection i join i.part p
            where r.status = com.capstone.inspection.domain.inspection.JudgementRequestStatus.OPEN
              and (:partCode is null or p.partCode = :partCode)""")
    Page<JudgementRequest> searchOpen(String partCode, Pageable pageable);

    // 관리자 목록: 처리됨·전체, 최근 처리(처리 전이면 요청) 시각부터
    @Query(value = """
            select r from JudgementRequest r join fetch r.inspection i join fetch i.part p
              join fetch r.requestedBy left join fetch r.resolvedBy
            where r.status in :statuses
              and (:partCode is null or p.partCode = :partCode)
            order by coalesce(r.resolvedAt, r.requestedAt) desc, r.id desc""",
            countQuery = """
            select count(r) from JudgementRequest r join r.inspection i join i.part p
            where r.status in :statuses
              and (:partCode is null or p.partCode = :partCode)""")
    Page<JudgementRequest> searchRecent(Collection<JudgementRequestStatus> statuses, String partCode,
                                        Pageable pageable);

    // 처리 기록. 대기 중일 때만 갱신되므로 동시 처리 중 1건만 1을 받음
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
            update JudgementRequest r set r.status = :status, r.resolvedBy = :user, r.resolvedAt = :at,
                   r.resolveNote = :note
            where r.id = :id and r.status = com.capstone.inspection.domain.inspection.JudgementRequestStatus.OPEN""")
    int markResolved(String id, JudgementRequestStatus status, User user, LocalDateTime at, String note);
}
