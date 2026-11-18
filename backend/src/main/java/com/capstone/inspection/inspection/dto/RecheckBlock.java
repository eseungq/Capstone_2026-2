package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.time.OffsetDateTime;

// AUTO_PASS 표본 재확인 1건 (계약 6.11). 상세의 recheck 블록과 재확인·확인함 응답에 같이 씀
//   시스템 판정(judgement 블록)과 별개. result가 FAIL이어도 원래 판정은 PASS·SYSTEM 그대로라 두 블록을 함께 표시
public record RecheckBlock(RecheckStratum stratum,
                           double samplingRate,
                           String ruleVersion,        // 결정에 쓴 규칙 (V8 기록이면 null)
                           String trialName,          // 시험 회차 (선택)
                           OffsetDateTime sampledAt,
                           Judgement result,          // 재확인 전이면 null
                           String comment,
                           String recheckedBy,        // 확인 작업자 loginId
                           OffsetDateTime recheckedAt,
                           String acknowledgedBy,     // 관리자 확인함 (해결 완료 아님), 확인 전이면 null
                           OffsetDateTime acknowledgedAt,
                           String acknowledgeNote) {

    public static RecheckBlock of(AutoPassRecheck r) {
        return new RecheckBlock(r.getStratum(), r.getSamplingRate(),
                r.getRule() == null ? null : r.getRule().getRuleVersion(),
                r.getRule() == null ? null : r.getRule().getTrialName(),
                Times.toOffset(r.getSampledAt()), r.getResult(), r.getComment(),
                r.getRecheckedBy() == null ? null : r.getRecheckedBy().getLoginId(), Times.toOffset(r.getRecheckedAt()),
                r.getAcknowledgedBy() == null ? null : r.getAcknowledgedBy().getLoginId(),
                Times.toOffset(r.getAcknowledgedAt()), r.getAcknowledgeNote());
    }
}
