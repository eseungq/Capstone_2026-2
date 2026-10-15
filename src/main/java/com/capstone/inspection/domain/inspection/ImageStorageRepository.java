package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ImageStorageRepository extends JpaRepository<ImageStorage, String> {

    Optional<ImageStorage> findByInspectionIdAndImageType(String inspectionId, ImageType imageType);

    List<ImageStorage> findByInspectionId(String inspectionId);
}
