package com.capstone.inspection.domain.model;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface AutomationPolicyRepository extends JpaRepository<AutomationPolicy, String> {

    // 모델 버전에 걸린 ready·active 정책 (보정기 버전 호환은 PolicyEvaluator에서 확인)
    @Query("select p from AutomationPolicy p where p.model.id = :modelId and p.ready = true and p.active = true")
    List<AutomationPolicy> findReadyActiveByModelId(String modelId);

    // 활성 모델에 걸린 ready·active 정책이 있는 검사항목 ID (모니터링·부품 목록의 policyActive)
    @Query("select distinct p.item.id from AutomationPolicy p where p.ready = true and p.active = true and p.model.active = true")
    List<String> findItemIdsWithActivePolicy();
}
