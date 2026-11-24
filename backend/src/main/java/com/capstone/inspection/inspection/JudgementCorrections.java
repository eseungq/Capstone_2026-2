package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.JudgementRequest;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

// 검사별 마지막 정정 고르기 (계약 6.12: 현재 판정 = 마지막 CORRECTED 요청의 판정)
//   처리 시각 순, 같으면 ID로 고정. 상세·이력·요청 검사가 같은 기준을 씀
final class JudgementCorrections {

    private static final Comparator<JudgementRequest> BY_RESOLVED =
            Comparator.comparing(JudgementRequest::getResolvedAt).thenComparing(JudgementRequest::getId);

    private JudgementCorrections() {
    }

    // CORRECTED 요청들 → 검사 ID별 마지막 정정
    static Map<String, JudgementRequest> latestByInspection(List<JudgementRequest> corrected) {
        return corrected.stream().collect(Collectors.toMap(r -> r.getInspection().getId(), r -> r,
                BinaryOperator.maxBy(BY_RESOLVED)));
    }

    // 한 검사의 CORRECTED 요청들 → 마지막 정정, 없으면 null
    static JudgementRequest latest(List<JudgementRequest> corrected) {
        return corrected.stream().max(BY_RESOLVED).orElse(null);
    }
}
