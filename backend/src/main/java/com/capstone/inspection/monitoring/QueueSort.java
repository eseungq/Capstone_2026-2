package com.capstone.inspection.monitoring;

// 확인 필요 목록 정렬 (계약 v4 6.4)
public enum QueueSort {
    RECEIVED, // 오래된 순 (기본)
    PRIORITY  // GOOD·기준 초과 REVIEW 먼저, 그룹 안은 오래된 순 [제안 11/23]
}
