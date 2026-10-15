package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface InspectionRepository extends JpaRepository<Inspection, String> {

    // 상세 조회용: 연관 엔티티 함께 로딩 (LAZY 프록시 직렬화 문제·N+1 방지)
    @Query("select i from Inspection i join fetch i.part join fetch i.item join fetch i.model "
            + "left join fetch i.policy where i.id = :id")
    Optional<Inspection> findDetailById(String id);

    // Idempotency-Key 재전송 확인
    @Query("select i from Inspection i join fetch i.part where i.user.id = :userId and i.clientRequestId = :key")
    Optional<Inspection> findByUserIdAndClientRequestId(String userId, String key);

    // 서버 재시작 시 남은 건 정리
    List<Inspection> findByStatus(InspectionStatus status);
}
