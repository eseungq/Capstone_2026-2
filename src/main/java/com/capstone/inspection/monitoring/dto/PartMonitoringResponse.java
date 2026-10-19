package com.capstone.inspection.monitoring.dto;

import com.capstone.inspection.inspection.DisplayState;

import java.time.OffsetDateTime;
import java.util.List;

// GET /monitoring/parts 응답의 부품 1개 (계약 v4 6.3)
public record PartMonitoringResponse(String partCode,
                                     String partName,
                                     boolean modelAvailable,     // 활성 모델 있음 (AI 서버 로드 확인은 이후 추가)
                                     boolean policyActive,       // 활성 모델에 ready·active 정책 있음
                                     OffsetDateTime lastReceivedAt,
                                     long pendingReviewCount,    // REVIEW_PENDING 건수 (배지용)
                                     long failedCount,           // 재검사하지 않은 FAILED 건수 (배지용)
                                     List<Recent> recent) {      // 최근 N건, 접수 시각 최신순

    public record Recent(String inspectionId, DisplayState displayState, OffsetDateTime receivedAt,
                         String thumbnailUrl) {
    }
}
