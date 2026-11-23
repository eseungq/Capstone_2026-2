package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.JudgementRequest;
import com.capstone.inspection.domain.inspection.JudgementRequestStatus;

import java.time.OffsetDateTime;

// 판정 확인 요청 1건 (계약 6.12). 요청·목록·처리 응답과 상세 judgementRequests 항목에 같이 씀
public record JudgementRequestResponse(String requestId,
                                       String inspectionId,
                                       String inspectionNo,
                                       String partCode,
                                       Judgement originalJudgement,  // 검사의 최초 판정 (judgement 블록 값)
                                       JudgedBy originalJudgedBy,
                                       Judgement currentJudgement,   // 요청 당시 현재 판정
                                       Judgement claimedJudgement,
                                       String area,
                                       String reason,
                                       String requestedBy,           // 요청 작업자 loginId
                                       OffsetDateTime requestedAt,
                                       JudgementRequestStatus status,
                                       String resolvedBy,            // 처리 관리자 loginId, 대기면 null
                                       OffsetDateTime resolvedAt,
                                       String resolveNote) {

    public static JudgementRequestResponse of(JudgementRequest r) {
        Inspection i = r.getInspection();
        return new JudgementRequestResponse(r.getId(), i.getId(), i.getInspectionNo(), i.getPart().getPartCode(),
                r.getOriginalJudgement(), i.getJudgedBy(), r.getCurrentJudgement(), r.getClaimedJudgement(),
                r.getArea(), r.getReason(), r.getRequestedBy().getLoginId(), Times.toOffset(r.getRequestedAt()),
                r.getStatus(), r.getResolvedBy() == null ? null : r.getResolvedBy().getLoginId(),
                Times.toOffset(r.getResolvedAt()), r.getResolveNote());
    }
}
