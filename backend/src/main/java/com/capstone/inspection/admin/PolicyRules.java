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

    // 새 버전 이름: 원본 이름 + -접미어번호. 같은 접미어의 기존 버전 중 가장 큰 번호 + 1
    //   접미어: t 기준치 조정, f 불량 기준 등록·조정, a 자동 불량 켜고 끄기 (계약 6.9)
    //   항상 원본 이름에 붙이므로 여러 번 바꿔도 이름이 길어지지 않음 (어느 버전에서 왔는지는 basedOnPolicyId)
    static String nextVersion(String rootVersion, String suffix, Collection<String> existingVersions) {
        String prefix = rootVersion + "-" + suffix;
        Pattern pattern = Pattern.compile(Pattern.quote(prefix) + "(\\d+)");
        int max = 0;
        for (String version : existingVersions) {
            Matcher matcher = pattern.matcher(version);
            if (matcher.matches()) {
                max = Math.max(max, Integer.parseInt(matcher.group(1)));
            }
        }
        return prefix + (max + 1);
    }

    // DB 컬럼(DECIMAL(7,6))과 같은 소수 6자리로 맞춤. 반올림은 크기 순서를 바꾸지 않으므로 범위 검사는 맞춘 값으로 함
    static double round6(double value) {
        return BigDecimal.valueOf(value).setScale(6, RoundingMode.HALF_UP).doubleValue();
    }
}
