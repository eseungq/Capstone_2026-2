package com.capstone.inspection.domain.inspection;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

// 표본 재확인 추출 규칙 기록 (계약 6.11, V9 recheck_rule). 같은 값·같은 시험 이름이면 같은 행
//   AUTO_PASS 판정 때 검사에 연결하고(inspection.recheck_rule_id), 추출 결정도 이 규칙으로 함
@Entity
@Table(name = "recheck_rule")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RecheckRuleSnapshot {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 60)
    private String ruleVersion;

    @Column(length = 60)
    private String trialName;           // 같은 설정의 시험 회차 구분 (선택)

    @Column(nullable = false)
    private double nearRatio;

    @Column(nullable = false)
    private double midRatio;

    @Column(nullable = false)
    private double nearRate;

    @Column(nullable = false)
    private double midRate;

    @Column(nullable = false)
    private double lowRate;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    public RecheckRuleSnapshot(RecheckRule rule, String trialName) {
        this.id = UUID.randomUUID().toString();
        this.ruleVersion = rule.version();
        this.trialName = trialName;
        this.nearRatio = rule.nearRatio();
        this.midRatio = rule.midRatio();
        this.nearRate = rule.nearRate();
        this.midRate = rule.midRate();
        this.lowRate = rule.lowRate();
        this.createdAt = LocalDateTime.now().truncatedTo(ChronoUnit.MICROS);
    }

    public RecheckRule toRule() {
        return new RecheckRule(nearRatio, midRatio, nearRate, midRate, lowRate);
    }
}
