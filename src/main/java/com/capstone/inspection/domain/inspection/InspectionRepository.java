package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface InspectionRepository extends JpaRepository<Inspection, String>, JpaSpecificationExecutor<Inspection> {

    // 상세 조회용: 연관 엔티티 함께 로딩 (LAZY 프록시 직렬화 문제·N+1 방지)
    @Query("select i from Inspection i join fetch i.part join fetch i.item join fetch i.model "
            + "left join fetch i.policy where i.id = :id")
    Optional<Inspection> findDetailById(String id);

    // Idempotency-Key 재전송 확인
    @Query("select i from Inspection i join fetch i.part where i.user.id = :userId and i.clientRequestId = :key")
    Optional<Inspection> findByUserIdAndClientRequestId(String userId, String key);

    // 서버 재시작 시 남은 건 정리
    List<Inspection> findByStatus(InspectionStatus status);

    // ---- 모니터링 (계약 6.3). 건수는 화면 배지용이며 통계로 확장하지 않음 ----

    record PartCount(String partId, long count) {
    }

    record PartLastReceived(String partId, LocalDateTime receivedAt) {
    }

    @Query("select new com.capstone.inspection.domain.inspection.InspectionRepository$PartLastReceived(i.part.id, max(i.receivedAt)) "
            + "from Inspection i group by i.part.id")
    List<PartLastReceived> findLastReceivedByPart();

    @Query("select new com.capstone.inspection.domain.inspection.InspectionRepository$PartCount(i.part.id, count(i)) "
            + "from Inspection i where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED "
            + "and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.REVIEW "
            + "and i.finalJudgement is null group by i.part.id")
    List<PartCount> countReviewPendingByPart();

    // 아직 재검사하지 않은 FAILED만
    @Query("select new com.capstone.inspection.domain.inspection.InspectionRepository$PartCount(i.part.id, count(i)) "
            + "from Inspection i where i.status = com.capstone.inspection.domain.inspection.InspectionStatus.FAILED "
            + "and not exists (select r.id from Inspection r where r.retryOfInspectionId = i.id) group by i.part.id")
    List<PartCount> countFailedNotRetriedByPart();

    // 부품별 최근 n건의 ID (접수 시각 최신순). LATERAL로 부품마다 idx_insp_part_received를 따라 n건만 읽음
    @Query(value = "SELECT r.id FROM part p JOIN LATERAL (SELECT i.id FROM inspection i WHERE i.part_id = p.id "
            + "ORDER BY i.received_at DESC, i.id DESC LIMIT :n) r ON TRUE", nativeQuery = true)
    List<String> findRecentIdsPerPart(int n);

    // 작업자 판정 기록. 아직 판정 전인 REVIEW 건일 때만 갱신되므로 동시 제출 중 1건만 1을 받음 (계약 6.7)
    @Modifying(flushAutomatically = true)
    @Query("update Inspection i set i.finalJudgement = :judgement, i.judgedBy = com.capstone.inspection.domain.inspection.JudgedBy.WORKER "
            + "where i.id = :id and i.status = com.capstone.inspection.domain.inspection.InspectionStatus.COMPLETED "
            + "and i.recommendedAction = com.capstone.inspection.domain.inspection.RecommendedAction.REVIEW "
            + "and i.finalJudgement is null")
    int markWorkerJudgement(String id, Judgement judgement);
}
