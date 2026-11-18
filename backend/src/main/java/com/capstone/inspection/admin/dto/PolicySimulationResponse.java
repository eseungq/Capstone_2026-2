package com.capstone.inspection.admin.dto;

import com.capstone.inspection.admin.PolicySimulation;

// 정책 후보 비교 결과 (계약 6.9.1). 조회만 하며 정책·검사 기록은 바꾸지 않음
public record PolicySimulationResponse(String policyId,
                                       String policyVersion,
                                       String partCode,
                                       String modelVersion,
                                       String calibratorVersion,
                                       double currentThreshold,
                                       double candidateThreshold,
                                       Double validatedMin,
                                       Double validatedMax,
                                       boolean candidateWithinValidatedRange,
                                       long evaluatedCount,
                                       long defectPredictedCount,
                                       PolicySimulation.Outcome current,
                                       PolicySimulation.Outcome candidate,
                                       PolicySimulation.Change change) {
}
