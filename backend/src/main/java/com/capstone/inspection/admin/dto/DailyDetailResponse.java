package com.capstone.inspection.admin.dto;

import com.capstone.inspection.domain.inspection.Judgement;

import java.time.LocalDate;
import java.util.List;

// 기준 상세 (계약 6.13): 날짜 행 하나(같은 날짜·정책)의 기준 주변 REVIEW
//   passBand: GOOD 예측 REVIEW 중 passThreshold < 확률 ≤ passThreshold + band
//   failBand: DEFECT 예측 REVIEW 중 failThreshold − band ≤ 확률 < failThreshold. 불량 기준이 없으면 null
//   reference: 기준 라벨·실물 확인 결과 저장처가 없어 항상 null (TBD-20)
public record DailyDetailResponse(
        LocalDate date,
        String partCode,
        String policyId,
        String policyVersion,
        String modelVersion,
        String calibratorVersion,
        Double passThreshold,
        Double failThreshold,
        boolean autoFailEnabled,
        double band,
        Band passBand,
        Band failBand,
        Object reference) {

    // pass + fail + pending = total. items는 확률 오름차순
    public record Band(double from, double to, int total, int pass, int fail, int pending, List<Item> items) {
    }

    // correctedJudgement: 판정 확인 요청으로 정정된 판정, 없으면 null
    public record Item(String inspectionId, String inspectionNo, Double calibratedDefectProbability,
                       Judgement finalJudgement, Judgement correctedJudgement) {
    }
}
