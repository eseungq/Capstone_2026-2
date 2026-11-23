package com.capstone.inspection.domain.inspection;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.Optional;

public interface RecheckRuleSnapshotRepository extends JpaRepository<RecheckRuleSnapshot, String> {

    // 시험 이름 없음(null)도 같은 값이면 같은 행 (DB는 trial_key UNIQUE)
    @Query("""
            select r from RecheckRuleSnapshot r where r.ruleVersion = :ruleVersion
              and ((:trialName is null and r.trialName is null) or r.trialName = :trialName)""")
    Optional<RecheckRuleSnapshot> findByVersionAndTrial(String ruleVersion, String trialName);
}
