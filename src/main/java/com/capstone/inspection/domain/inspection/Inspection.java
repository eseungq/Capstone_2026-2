package com.capstone.inspection.domain.inspection;

import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AutomationPolicy;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.user.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

// 검사 1건. AI 예측, 정책 적용 결과, 최종 판정을 함께 보관 (작업자 확인 기록은 WorkerConfirmation에 분리)
// 상태 전이: RECEIVED → ANALYZING → COMPLETED(AUTO_PASS·REVIEW) 또는 FAILED (계약 v4 3장)
@Entity
@Table(name = "inspection")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Inspection {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, unique = true, length = 20)
    private String inspectionNo;                 // 화면 표시용 번호 INS-000001

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id")
    private User user;                           // 접수 계정 (DEVICE·ADMIN), 재검사면 요청자

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 10)
    private InspectionSource source;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "part_id")
    private Part part;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "item_id")
    private InspectionItem item;

    @Column(length = 30)
    private String lineCode;                     // 향후 라인별 통계 대비 (지금은 null 허용)

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "model_id")
    private AiModel model;                       // 호출한 모델 버전

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "policy_id")
    private AutomationPolicy policy;             // 판정에 사용한 호환 정책, 없으면 null

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private InspectionStatus status;

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private PredictedQuality predictedQuality;   // AI 사진 단위 예측

    private Double rawDefectProbability;         // 보정 전 점수 (명칭 TBD-07)

    private Double calibratedDefectProbability;  // 보정 불량 확률, 미준비면 null

    @Column(length = 100)
    private String calibratorVersion;            // AI 응답의 보정기 버전

    private Boolean patchInspectionSupported;    // v3 이전 기록용. 신규 기록에서는 사용하지 않음

    @Column(nullable = false)
    private boolean automationPolicyReady;       // 호환되는 ready·active 정책이 있었는지

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private RecommendedAction recommendedAction; // COMPLETED에서만 값

    @Enumerated(EnumType.STRING)
    @Column(length = 30)
    private ReviewReason reviewReason;           // REVIEW일 때 사유 1개

    private Double passThresholdApplied;         // 판정 당시 기준치 스냅숏

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Judgement finalJudgement;            // AUTO_PASS면 PASS, REVIEW는 작업자 확인 후

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private JudgedBy judgedBy;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private GradcamStatus gradcamStatus;

    private Integer inferenceTimeMs;             // AI 처리 시간

    @Column(length = 40)
    private String errorCode;                    // FAILED 사유 (ErrorCode 이름)

    @Column(length = 1000)
    private String errorDetail;                  // AI 오류 코드·메시지 등 (앱에는 노출하지 않음)

    @Column(columnDefinition = "json")
    private String aiResponseJson;               // AI 응답 원문 (Grad-CAM 이미지 데이터 제외)

    @Column(length = 36)
    private String retryOfInspectionId;          // 재검사면 원래 FAILED 검사 ID

    @Column(length = 100)
    private String clientRequestId;              // Idempotency-Key

    @Column(length = 32)
    private String traceId;                      // 접수 요청 traceId (분석 로그 연결)

    private LocalDateTime capturedAt;            // 촬영(모사) 시각

    @Column(nullable = false)
    private LocalDateTime receivedAt;            // 접수 시각 (목록 정렬 기준)

    private LocalDateTime startedAt;             // 분석 시작

    private LocalDateTime completedAt;           // COMPLETED·FAILED 확정 시각

    // 접수: 원본 저장과 같은 트랜잭션에서 RECEIVED로 생성
    public Inspection(String inspectionNo, User user, InspectionSource source, Part part, InspectionItem item,
                      AiModel model, String lineCode, LocalDateTime capturedAt, String clientRequestId,
                      String retryOfInspectionId, String traceId) {
        this.id = UUID.randomUUID().toString();
        this.inspectionNo = inspectionNo;
        this.user = user;
        this.source = source;
        this.part = part;
        this.item = item;
        this.model = model;
        this.lineCode = lineCode;
        this.clientRequestId = clientRequestId;
        this.retryOfInspectionId = retryOfInspectionId;
        this.traceId = traceId;
        this.status = InspectionStatus.RECEIVED;
        this.automationPolicyReady = false;
        this.receivedAt = LocalDateTime.now();
        this.capturedAt = capturedAt != null ? capturedAt : this.receivedAt; // 없으면 접수 시각 (계약 6.2)
    }

    public void startAnalysis() {
        this.status = InspectionStatus.ANALYZING;
        this.startedAt = LocalDateTime.now();
    }

    // AI 결과 기록 (정책 적용 전 값)
    public void recordAiResult(PredictedQuality predictedQuality, double rawDefectProbability,
                               Double calibratedDefectProbability, String calibratorVersion,
                               int inferenceTimeMs, String aiResponseJson) {
        this.predictedQuality = predictedQuality;
        this.rawDefectProbability = rawDefectProbability;
        this.calibratedDefectProbability = calibratedDefectProbability;
        this.calibratorVersion = calibratorVersion;
        this.inferenceTimeMs = inferenceTimeMs;
        this.aiResponseJson = aiResponseJson;
    }

    // 정책 적용 결과로 COMPLETED 확정. AUTO_PASS면 최종 PASS(SYSTEM)까지 기록
    public void complete(RecommendedAction action, ReviewReason reviewReason, AutomationPolicy policy,
                         Double passThresholdApplied, GradcamStatus gradcamStatus) {
        this.status = InspectionStatus.COMPLETED;
        this.recommendedAction = action;
        this.reviewReason = action == RecommendedAction.REVIEW ? reviewReason : null;
        this.policy = policy;
        this.automationPolicyReady = policy != null;
        this.passThresholdApplied = passThresholdApplied;
        this.gradcamStatus = gradcamStatus;
        if (action == RecommendedAction.AUTO_PASS) {
            this.finalJudgement = Judgement.PASS;
            this.judgedBy = JudgedBy.SYSTEM;
        }
        this.completedAt = LocalDateTime.now();
    }

    // 분석 실패. recommendedAction·finalJudgement는 null 유지 (계약 3.2)
    public void fail(String errorCode, String errorDetail) {
        this.status = InspectionStatus.FAILED;
        this.errorCode = errorCode;
        this.errorDetail = errorDetail == null ? null
                : errorDetail.substring(0, Math.min(errorDetail.length(), 1000));
        this.recommendedAction = null;
        this.finalJudgement = null;
        this.judgedBy = null;
        this.reviewReason = null;
        this.completedAt = LocalDateTime.now();
    }

    public boolean isFinished() {
        return status == InspectionStatus.COMPLETED || status == InspectionStatus.FAILED;
    }
}
