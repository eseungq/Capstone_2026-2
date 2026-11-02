package com.capstone.inspection.admin;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Collection;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// 정책 등록·조정 규칙 (계약 v4 6.9)
final class PolicyRules {

    private PolicyRules() {
    }

    // ready 판정 (TBD-03 임시). 관리자가 지정하지 않고 등록 자료로 결정
    //   보정기 버전이 있고 모델의 보정기와 일치, 표본 수가 기준 이상. 기준치·검증 범위는 요청 검증에서 이미 확인함
    static boolean isReady(String requestCalibrator, String modelCalibrator, JsonNode metrics, int minSampleCount) {
        if (requestCalibrator == null || !Objects.equals(requestCalibrator, modelCalibrator)) {
            return false;
        }
        JsonNode sampleCount = metrics == null ? null : metrics.get("sampleCount");
        return sampleCount != null && sampleCount.isNumber() && sampleCount.asLong() >= minSampleCount;
    }

    // 조정 버전 이름: 원본 이름 + -t번호. 기존 조정 버전 중 가장 큰 번호 + 1
    static String nextVersion(String rootVersion, Collection<String> existingVersions) {
        Pattern pattern = Pattern.compile(Pattern.quote(rootVersion) + "-t(\\d+)");
        int max = 0;
        for (String version : existingVersions) {
            Matcher matcher = pattern.matcher(version);
            if (matcher.matches()) {
                max = Math.max(max, Integer.parseInt(matcher.group(1)));
            }
        }
        return rootVersion + "-t" + (max + 1);
    }

    // DB 컬럼(DECIMAL(7,6))과 같은 소수 6자리로 맞춤. 반올림은 크기 순서를 바꾸지 않으므로 범위 검사는 맞춘 값으로 함
    static double round6(double value) {
        return BigDecimal.valueOf(value).setScale(6, RoundingMode.HALF_UP).doubleValue();
    }
}
