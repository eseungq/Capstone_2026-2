package com.capstone.inspection.domain.inspection;

import java.math.BigDecimal;

// 표본 재확인 추출 규칙 값 (계약 6.11). 결정할 때 쓴 규칙을 recheck_rule에 남겨 설정이 다른 기간을 섞지 않음
//   version은 값으로 만든 이름이라 같은 값이면 항상 같음. 순서 고정: b(MID 경계-NEAR 경계, %) p(NEAR-MID-LOW 비율, %)
//   예: v1-b40-80-p100-30-10. 추출 해시나 경계 포함 규칙(r ≥ 경계)이 바뀌면 SCHEME을 올림 [합의 11/18 김도현]
public record RecheckRule(double nearRatio, double midRatio, double nearRate, double midRate, double lowRate) {

    public static final String SCHEME = "v1";

    // 아무것도 뽑지 않는 규칙 (재확인 설정이 없을 때 예상 재확인 건수 0)
    public static final RecheckRule NONE = new RecheckRule(0, 0, 0, 0, 0);

    public String version() {
        return SCHEME + "-b" + percent(midRatio) + "-" + percent(nearRatio) + "-p" + percent(nearRate) + "-"
                + percent(midRate) + "-" + percent(lowRate);
    }

    public double rateOf(RecheckStratum stratum) {
        return switch (stratum) {
            case NEAR -> nearRate;
            case MID -> midRate;
            case LOW -> lowRate;
        };
    }

    private static String percent(double value) {
        return BigDecimal.valueOf(value).movePointRight(2).stripTrailingZeros().toPlainString();
    }
}
