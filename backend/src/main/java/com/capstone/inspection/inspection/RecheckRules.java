package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.nio.charset.StandardCharsets;

// AUTO_PASS 표본 재확인 추출 규칙 (계약 6.11)
//   - 구간: r = 보정 확률 ÷ 판정 당시 기준치 (0 ≤ r ≤ 1). 부품마다 기준치가 달라도 같은 규칙
//   - 추출: 검사 ID로 정한 0~1 값이 구간 비율보다 작으면 뽑음. 같은 검사·같은 설정이면 항상 같은 결과라
//     다시 돌려도 재현되고, 사람이 문제가 보이는 건만 골라 넣을 수 없음 (대표성 유지)
//   - 계약 6.9.1 후보 비교의 예상 재확인 건수도 같은 규칙으로 계산 (admin 패키지에서 사용)
public final class RecheckRules {

    public record Decision(RecheckStratum stratum, double rate, double ratio, double draw, boolean sampled) {
    }

    // 나눗셈 오차 보정 (0.04 / 0.05 = 0.7999999999999999). 확률·기준치는 소수 6자리라 이 크기로는 구간이 잘못 바뀌지 않음
    private static final double EPSILON = 1e-9;

    private RecheckRules() {
    }

    public static Decision decide(String inspectionId, double calibrated, double threshold, RecheckRule rule) {
        double ratio = ratio(calibrated, threshold);
        RecheckStratum stratum = stratumOf(ratio, rule);
        double rate = rule.rateOf(stratum);
        double draw = draw(inspectionId);
        return new Decision(stratum, rate, ratio, draw, rate > 0 && draw < rate);
    }

    public static RecheckStratum stratum(double calibrated, double threshold, RecheckRule rule) {
        return stratumOf(ratio(calibrated, threshold), rule);
    }

    // 기준치 0이면 통과 건은 확률 0뿐이라 기준 근처로 봄
    static double ratio(double calibrated, double threshold) {
        return threshold > 0 ? calibrated / threshold : 1.0;
    }

    private static RecheckStratum stratumOf(double r, RecheckRule rule) {
        if (r + EPSILON >= rule.nearRatio()) {
            return RecheckStratum.NEAR;
        }
        return r + EPSILON >= rule.midRatio() ? RecheckStratum.MID : RecheckStratum.LOW;
    }

    // 검사 ID의 SHA-256 앞 52비트를 [0, 1)로 (double로 정확히 표현되는 범위)
    static double draw(String inspectionId) {
        String hex = Hashes.sha256(inspectionId.getBytes(StandardCharsets.UTF_8));
        return Long.parseLong(hex.substring(0, 13), 16) / (double) (1L << 52);
    }
}
