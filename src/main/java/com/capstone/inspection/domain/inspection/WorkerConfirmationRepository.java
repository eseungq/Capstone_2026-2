package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface WorkerConfirmationRepository extends JpaRepository<WorkerConfirmation, String> {

    @Query("select c from WorkerConfirmation c join fetch c.worker where c.inspection.id = :inspectionId")
    Optional<WorkerConfirmation> findByInspectionIdWithWorker(String inspectionId);

    // 목록 조회용: 여러 검사의 확인 기록을 한 번에 (N+1 방지)
    @Query("select c from WorkerConfirmation c where c.inspection.id in :inspectionIds")
    List<WorkerConfirmation> findByInspectionIds(Collection<String> inspectionIds);
}
