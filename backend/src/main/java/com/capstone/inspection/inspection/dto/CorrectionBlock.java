package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.JudgementRequest;

import java.time.OffsetDateTime;

// 검사의 마지막 정정 (계약 6.5 correction). judgement 블록(최초 판정)은 그대로라 "최초 → 정정"을 함께 표시
public record CorrectionBlock(String requestId,
                              Judgement correctedJudgement,
                              String correctedBy,          // 처리 관리자 loginId
                              OffsetDateTime correctedAt,
                              String note) {

    // CORRECTED 요청 → 정정 블록, 없으면 null
    public static CorrectionBlock of(JudgementRequest corrected) {
        if (corrected == null) {
            return null;
        }
        return new CorrectionBlock(corrected.getId(), corrected.getClaimedJudgement(),
                corrected.getResolvedBy().getLoginId(), Times.toOffset(corrected.getResolvedAt()),
                corrected.getResolveNote());
    }
}
