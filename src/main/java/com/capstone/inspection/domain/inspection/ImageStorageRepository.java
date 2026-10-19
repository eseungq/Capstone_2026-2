package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface ImageStorageRepository extends JpaRepository<ImageStorage, String> {

    Optional<ImageStorage> findByInspectionIdAndImageType(String inspectionId, ImageType imageType);

    List<ImageStorage> findByInspectionId(String inspectionId);

    // 목록 썸네일용: 여러 검사의 이미지를 한 번에 (N+1 방지)
    @Query("select s from ImageStorage s where s.inspection.id in :inspectionIds and s.imageType = :imageType")
    List<ImageStorage> findByInspectionIdsAndType(Collection<String> inspectionIds, ImageType imageType);
}
