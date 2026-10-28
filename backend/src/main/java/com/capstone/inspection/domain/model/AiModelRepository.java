package com.capstone.inspection.domain.model;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface AiModelRepository extends JpaRepository<AiModel, String> {

    // 활성 모델 전체 (검사항목 함께 조회)
    @Query("select m from AiModel m join fetch m.item where m.active = true")
    List<AiModel> findAllActiveWithItem();

    // 검사항목의 활성 모델 (접수 시 사용)
    @Query("select m from AiModel m where m.item.id = :itemId and m.active = true")
    List<AiModel> findActiveByItemId(String itemId);
}
