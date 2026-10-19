package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;

import java.time.OffsetDateTime;

// POST /inspections/{id}/confirm 응답 (계약 v4 6.7, 앱 판정 제출 결과 화면용)
public record ConfirmResponse(String inspectionId,
                              String inspectionNo,
                              PredictedQuality predictedQuality,
                              RecommendedAction recommendedAction,
                              Judgement finalJudgement,
                              JudgedBy judgedBy,
                              String confirmedBy,          // 확인한 작업자 loginId
                              OffsetDateTime confirmedAt) {

    public static ConfirmResponse of(Inspection i, WorkerConfirmation c) {
        return new ConfirmResponse(i.getId(), i.getInspectionNo(), i.getPredictedQuality(), i.getRecommendedAction(),
                c.getFinalJudgement(), JudgedBy.WORKER, c.getWorker().getLoginId(), Times.toOffset(c.getConfirmedAt()));
    }
}
