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
import java.util.UUID;
import com.capstone.inspection.common.time.Times;

// 자동 통과·자동 불량 정책 1개 버전. 관리자가 기준을 바꾸면 행을 고치지 않고 새 버전을 만듦 (계약 v4 6.9)
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

    @Column(nullable = false)
    private boolean autoFailEnabled;    // 자동 불량 켜짐 (V13, 기본 false). 켜려면 failThreshold 필수

    private Double failThreshold;       // 자동 불량 하한 (DEFECT 예측 + 보정 불량 확률 ≥ 이 값이면 AUTO_FAIL)

    private Double failValidatedMin;    // AI가 검증한 불량 기준 범위
    private Double failValidatedMax;

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

    // 등록·기준치 조정으로 만드는 새 버전. 항상 active=false로 시작 (계약 v4 6.9)
    public AutomationPolicy(AiModel model, String calibratorVersion, String policyVersion, Double passThreshold,
                            Double validatedMin, Double validatedMax, String metricsJson, boolean ready,
                            String basedOnPolicyId) {
        this.id = UUID.randomUUID().toString();
        this.model = model;
        this.item = model.getItem();
        this.calibratorVersion = calibratorVersion;
        this.policyVersion = policyVersion;
        this.passThreshold = passThreshold;
        this.validatedMin = validatedMin;
        this.validatedMax = validatedMax;
        this.metricsJson = metricsJson;
        this.ready = ready;
        this.active = false;
        this.autoFailEnabled = false; // 자동 불량은 기본 꺼짐 (계약 4.1)
        this.basedOnPolicyId = basedOnPolicyId;
        this.createdAt = Times.now();
    }

    // 기준치 조정 새 버전: 통과 기준만 바꾸고 자동 불량 값은 이어받음 (계약 6.9)
    public AutomationPolicy withPassThreshold(String newVersion, double newPassThreshold) {
        AutomationPolicy next = nextVersion(newVersion);
        next.passThreshold = newPassThreshold;
        return next;
    }

    // 불량 기준 등록·조정 새 버전: 켜짐 여부는 이어받음
    public AutomationPolicy withFailThreshold(String newVersion, double newFailThreshold, double min, double max) {
        AutomationPolicy next = nextVersion(newVersion);
        next.failThreshold = newFailThreshold;
        next.failValidatedMin = min;
        next.failValidatedMax = max;
        return next;
    }

    // 자동 불량 켜고 끄기 새 버전: 기준은 그대로
    public AutomationPolicy withAutoFail(String newVersion, boolean enabled) {
        AutomationPolicy next = nextVersion(newVersion);
        next.autoFailEnabled = enabled;
        return next;
    }

    // 이 정책의 값을 모두 복사한 새 버전. active=false로 시작하고 basedOn은 이 정책
    private AutomationPolicy nextVersion(String newVersion) {
        AutomationPolicy next = new AutomationPolicy(model, calibratorVersion, newVersion, passThreshold,
                validatedMin, validatedMax, metricsJson, ready, id);
        next.autoFailEnabled = autoFailEnabled;
        next.failThreshold = failThreshold;
        next.failValidatedMin = failValidatedMin;
        next.failValidatedMax = failValidatedMax;
        return next;
    }

    public void activate(LocalDateTime at) {
        this.active = true;
        this.activatedAt = at;
    }

    public void deactivate() {
        this.active = false;
    }

    // 응답의 보정기 버전과 호환되는지 (정책에 보정기 버전이 없으면 보정 확률을 쓸 수 없으므로 비호환)
    public boolean isCompatibleWith(String responseCalibratorVersion) {
        return calibratorVersion != null && calibratorVersion.equals(responseCalibratorVersion);
    }
}
