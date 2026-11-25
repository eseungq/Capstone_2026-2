package com.capstone.inspection.admin.dto;

import java.time.LocalDate;

// 날짜별 이력 1행 (계약 6.13): KST 날짜 × 판정 당시 정책·모델·보정기 조합
//   정책 없는 행(정책 없음 REVIEW·수동 전환·분석 실패)은 정책 값이 null, autoFailEnabled = false
//   total = autoPass + autoFail + review.total. review에는 수동 전환이 포함되고 manual은 그중 수동 전환만 (분석 실패는 제외)
//   AI의 REVIEW 비율은 수동 전환과 FAILED를 빼고 계산: (review.total − manual.total) ÷ (total − manual.total)
public record DailyHistoryRow(
        LocalDate date,
        String policyId,
        String policyVersion,
        String modelVersion,
        String calibratorVersion,
        Double passThreshold,
        Double failThreshold,
        boolean autoFailEnabled,
        int total,
        int autoPass,
        int autoFail,
        Progress review,
        Progress manual,
        int failed,
        ConfirmedOpposite confirmedOpposite,
        int openRequests) {

    // 배정 건 중 조회 시점까지 작업자 판정이 끝난 수
    public record Progress(int done, int total) {
    }

    // 판정 확인 요청 중 처리된 것만. 검사 ID당 1건 (TBD-19)
    public record ConfirmedOpposite(int autoPassThenFail, int autoFailThenPass, int resolvedRequests) {
    }
}
