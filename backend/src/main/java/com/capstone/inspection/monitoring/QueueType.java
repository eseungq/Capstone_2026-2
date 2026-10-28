package com.capstone.inspection.monitoring;

// 확인 필요 목록 종류 (계약 v4 6.4)
public enum QueueType {
    REVIEW, // REVIEW_PENDING
    FAILED, // 재검사하지 않은 FAILED
    ALL
}
