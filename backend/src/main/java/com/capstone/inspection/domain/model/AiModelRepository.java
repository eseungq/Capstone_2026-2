package com.capstone.inspection.domain.model;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface AiModelRepository extends JpaRepository<AiModel, String> {

    // 활성 모델 전체 (검사항목 함께 조회)
    @Query("select m from AiModel m join fetch m.item where m.active = true")
    List<AiModel> findAllActiveWithItem();

    // 검사항목의 활성 모델 (접수 시 사용)
    @Query("select m from AiModel m where m.item.id = :itemId and m.active = true")
    List<AiModel> findActiveByItemId(String itemId);

    Optional<AiModel> findByModelVersion(String modelVersion);

    // 관리자 모델 목록 (부품 함께 조회)
    @Query("select m from AiModel m join fetch m.item i join fetch i.part order by m.modelVersion")
    List<AiModel> findAllWithPart();

    // 정책 적용 시 같은 모델의 동시 처리를 줄 세움
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select m from AiModel m where m.id = :id")
    Optional<AiModel> findByIdForUpdate(String id);
}
