package com.capstone.inspection.domain.inspection;

// AUTO_PASS 표본 재확인 구간 (계약 6.11). 보정 확률 ÷ 판정 당시 기준치로 나눔
public enum RecheckStratum {
    NEAR,   // 기준 근처
    MID,
    LOW     // 낮은 점수. 기준 근처만 보면 전체 통과 건을 대표하지 못하므로 일부는 반드시 뽑음
}
