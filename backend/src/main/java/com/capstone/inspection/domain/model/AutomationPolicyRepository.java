package com.capstone.inspection.domain.model;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface AutomationPolicyRepository extends JpaRepository<AutomationPolicy, String> {

    // 모델 버전에 걸린 ready·active 정책 (보정기 버전 호환은 PolicyEvaluator에서 확인)
    @Query("select p from AutomationPolicy p where p.model.id = :modelId and p.ready = true and p.active = true")
    List<AutomationPolicy> findReadyActiveByModelId(String modelId);

    // 활성 모델에 걸린 ready·active 정책이 있는 검사항목 ID (모니터링·부품 목록의 policyActive)
    @Query("select distinct p.item.id from AutomationPolicy p where p.ready = true and p.active = true and p.model.active = true")
    List<String> findItemIdsWithActivePolicy();

    // 관리자 정책 목록: 최신 생성순. 필터 값이 null이면 조건을 적용하지 않음
    @Query("""
            select p from AutomationPolicy p join fetch p.model join fetch p.item i join fetch i.part pt
            where (:partCode is null or pt.partCode = :partCode) and (:active is null or p.active = :active)
            order by p.createdAt desc, p.id""")
    List<AutomationPolicy> search(String partCode, Boolean active);

    boolean existsByPolicyVersion(String policyVersion);

    // 조정 버전 이름의 다음 번호를 정할 때 사용
    @Query("select p.policyVersion from AutomationPolicy p where p.policyVersion like concat(:prefix, '%')")
    List<String> findVersionsStartingWith(String prefix);

    // 같은 모델의 다른 active 정책 중지 (V5 uq_policy_active_model: 모델당 active 1개)
    @Modifying(flushAutomatically = true)
    @Query("update AutomationPolicy p set p.active = false where p.model.id = :modelId and p.active = true and p.id <> :keepId")
    int deactivateOthers(String modelId, String keepId);
}
