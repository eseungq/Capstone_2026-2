package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;

// 재확인 제출 결과: 원래 시스템 판정과 재확인 결과를 함께 반환 (계약 6.11)
public record RecheckResponse(String inspectionId,
                              String inspectionNo,
                              Judgement finalJudgement,   // 항상 PASS (바뀌지 않음)
                              JudgedBy judgedBy,          // 항상 SYSTEM
                              RecheckBlock recheck) {
}
