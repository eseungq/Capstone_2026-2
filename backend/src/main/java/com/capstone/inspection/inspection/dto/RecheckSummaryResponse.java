package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.time.OffsetDateTime;
import java.util.List;

// GET /admin/rechecks/summary 응답 (계약 6.11). 공동시험 비교용, 조회만
//   대기(pending)는 정상·불량 어느 쪽으로도 세지 않음. 완료 건이 없으면 비율·추정값은 null
//   화면 표시 [합의 11/18 김도현]: 추정값은 "AUTO_PASS 추정 불량률", 구간별 "완료 n/m건(완료율)",
//   partial이면 "일부만 완료되어 결과가 치우칠 수 있음" 안내
public record RecheckSummaryResponse(String partCode,
                                     OffsetDateTime from,
                                     OffsetDateTime to,
                                     long autoPassCount,
                                     long decidedCount,
                                     long undecidedCount,      // 결정 행 없음 (기능 꺼짐·저장 실패·재처리 전)
                                     long undecidedWithoutRuleCount, // 그중 판정 당시 규칙이 없는 건 (기능 꺼짐 등)
                                     List<RuleSummary> rules,  // 추출 규칙별로 따로 (섞지 않음)
                                     Waits waits,
                                     Dwell dwell) {

    public static final String UNRECORDED = "UNRECORDED"; // V8로 기록돼 규칙 값이 없는 결정

    // autoPassCount = decidedCount + undecidedCount (이 규칙으로 판정된 AUTO_PASS)
    public record RuleSummary(String ruleVersion, String trialName,
                              Double nearRatio, Double midRatio, Double nearRate, Double midRate, Double lowRate,
                              long autoPassCount, long decidedCount, long undecidedCount, long sampledCount,
                              long pendingCount, long passCount, long failCount,
                              Double completionRate,           // 완료 ÷ 뽑힌 건, 뽑힌 건이 없으면 null
                              boolean partial,                 // 재확인 대기 또는 결정 누락이 남음 → 추정이 치우칠 수 있음
                              List<StratumSummary> strata,
                              Double estimatedDefectRateInAutoPass,
                              Compare compare) {               // 비교 비율을 주지 않았으면 null
    }

    // completedCount = passCount + failCount, pendingCount = sampledCount - completedCount
    //   completionRate = completedCount ÷ sampledCount (뽑힌 건이 없으면 null)
    public record StratumSummary(RecheckStratum stratum, long autoPassCount, long decidedCount, long undecidedCount,
                                 long sampledCount, long completedCount, long pendingCount, Double completionRate,
                                 long passCount, long failCount, Double failRateAmongCompleted) {
    }

    // 가상 비교: 같은 기록에서 drawValue < 비교 비율인 건이 그 비율로 뽑혔을 건. 실제 재확인 결과가 있는 건만 PASS·FAIL,
    //   결과가 없는 건은 unverifiedCount. 비교 비율이 실제보다 큰 구간이 있으면 계산 불가 (computable false, 숫자 null)
    //   partial: 미확인(unverified) 또는 결정 누락이 남음 (계산 불가면 null)
    public record Compare(double nearRate, double midRate, double lowRate, boolean computable,
                          Long sampledCount, Long unverifiedCount, Long passCount, Long failCount,
                          Boolean partial, Double estimatedDefectRateInAutoPass) {
    }

    // 대기 시간: 완료된 건만 평균·중앙값, 아직 대기 중인 건은 pendingCount
    public record WaitStats(long count, long pendingCount, Long averageMs, Long medianMs) {
    }

    public record Waits(WaitStats review, WaitStats recheck) {
    }

    // 화면 체류 시간: 앱이 보낸 제출 건만 (미제출 이탈은 기록 없음)
    public record DwellStats(long count, Long averageMs, Long medianMs, Double averageOpenCount) {
    }

    public record Dwell(DwellStats review, DwellStats recheck) {
    }
}
