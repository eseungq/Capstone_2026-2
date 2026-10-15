package com.capstone.inspection.domain.model;

import com.capstone.inspection.domain.part.InspectionItem;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

// 자동 통과 정책 1개 버전. 관리자가 기준치를 조정하면 행을 고치지 않고 새 버전을 만듦 (계약 v4 6.9)
@Entity
@Table(name = "automation_policy")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AutomationPolicy {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "model_id")
    private AiModel model;              // 정책이 대응하는 모델 버전

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "item_id")
    private InspectionItem item;        // 정책이 대응하는 검사항목

    @Column(length = 100)
    private String calibratorVersion;   // 호환 보정기 버전. 응답의 calibratorVersion과 같아야 적용

    @Column(nullable = false, unique = true, length = 100)
    private String policyVersion;       // 예시 정책은 example- 접두어

    private Double targetMissRate;      // 이전 방식(목표 미검출률) 기록 보존용. 신규 정책은 null

    private Double passThreshold;       // 자동 통과 상한 (보정 불량 확률 ≤ 이 값이면 AUTO_PASS)

    private Double validatedMin;        // AI가 검증한 조정 가능 범위
    private Double validatedMax;

    @Column(nullable = false, columnDefinition = "json")
    private String metricsJson;         // AI 평가 근거

    @Column(nullable = false)
    private boolean ready;              // 검증 기준 충족 여부. 등록 시 결정, 관리자가 임의 지정 불가 (TBD-03)

    @Column(nullable = false)
    private boolean active;             // 현재 적용 중인지 (ready=true만 가능)

    @Column(length = 36)
    private String basedOnPolicyId;     // 기준 조정으로 만든 버전이면 원래 정책 ID

    @Column(nullable = false)
    private LocalDateTime createdAt;

    private LocalDateTime activatedAt;

    // 응답의 보정기 버전과 호환되는지 (정책에 보정기 버전이 없으면 보정 확률을 쓸 수 없으므로 비호환)
    public boolean isCompatibleWith(String responseCalibratorVersion) {
        return calibratorVersion != null && calibratorVersion.equals(responseCalibratorVersion);
    }
}
