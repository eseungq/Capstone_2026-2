package com.capstone.inspection.inspection;

import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.nio.charset.StandardCharsets;

// AUTO_PASS 표본 재확인 추출 규칙 (계약 6.11)
//   - 구간: r = 보정 확률 ÷ 판정 당시 기준치 (0 ≤ r ≤ 1). 부품마다 기준치가 달라도 같은 규칙
//   - 추출: 검사 ID로 정한 0~1 값이 구간 비율보다 작으면 뽑음. 같은 검사·같은 설정이면 항상 같은 결과라
//     다시 돌려도 재현되고, 사람이 문제가 보이는 건만 골라 넣을 수 없음 (대표성 유지)
final class RecheckRules {

    record Decision(RecheckStratum stratum, double rate, boolean sampled) {
    }

    // 나눗셈 오차 보정 (0.04 / 0.05 = 0.7999999999999999). 확률·기준치는 소수 6자리라 이 크기로는 구간이 잘못 바뀌지 않음
    private static final double EPSILON = 1e-9;

    private RecheckRules() {
    }

    static Decision decide(String inspectionId, double calibrated, double threshold, AppProperties.Recheck c) {
        RecheckStratum stratum = stratum(calibrated, threshold, c);
        double rate = switch (stratum) {
            case NEAR -> c.nearRate();
            case MID -> c.midRate();
            case LOW -> c.lowRate();
        };
        return new Decision(stratum, rate, rate > 0 && draw(inspectionId) < rate);
    }

    static RecheckStratum stratum(double calibrated, double threshold, AppProperties.Recheck c) {
        double r = threshold > 0 ? calibrated / threshold : 1.0; // 기준치 0이면 통과 건은 확률 0뿐이라 기준 근처로 봄
        if (r + EPSILON >= c.nearRatio()) {
            return RecheckStratum.NEAR;
        }
        return r + EPSILON >= c.midRatio() ? RecheckStratum.MID : RecheckStratum.LOW;
    }

    // 검사 ID의 SHA-256 앞 52비트를 [0, 1)로 (double로 정확히 표현되는 범위)
    static double draw(String inspectionId) {
        String hex = Hashes.sha256(inspectionId.getBytes(StandardCharsets.UTF_8));
        return Long.parseLong(hex.substring(0, 13), 16) / (double) (1L << 52);
    }
}
