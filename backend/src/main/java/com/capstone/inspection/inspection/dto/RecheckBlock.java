package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.time.OffsetDateTime;

// AUTO_PASS 표본 재확인 1건 (계약 6.11). 상세의 recheck 블록과 재확인 응답에 같이 씀
//   시스템 판정(judgement 블록)과 별개. result가 FAIL이어도 원래 판정은 PASS·SYSTEM 그대로
public record RecheckBlock(RecheckStratum stratum,
                           double samplingRate,
                           OffsetDateTime sampledAt,
                           Judgement result,          // 재확인 전이면 null
                           String comment,
                           String recheckedBy,        // 확인 작업자 loginId
                           OffsetDateTime recheckedAt) {

    public static RecheckBlock of(AutoPassRecheck r) {
        return new RecheckBlock(r.getStratum(), r.getSamplingRate(), Times.toOffset(r.getSampledAt()), r.getResult(),
                r.getComment(), r.getRecheckedBy() == null ? null : r.getRecheckedBy().getLoginId(),
                Times.toOffset(r.getRecheckedAt()));
    }
}
