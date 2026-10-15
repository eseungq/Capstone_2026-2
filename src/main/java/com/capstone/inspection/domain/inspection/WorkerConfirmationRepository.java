package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

public interface WorkerConfirmationRepository extends JpaRepository<WorkerConfirmation, String> {

    @Query("select c from WorkerConfirmation c join fetch c.worker where c.inspection.id = :inspectionId")
    Optional<WorkerConfirmation> findByInspectionIdWithWorker(String inspectionId);
}
