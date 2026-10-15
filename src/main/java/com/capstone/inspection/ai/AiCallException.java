package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.ErrorCode;

// AI 호출·응답 실패. 검사를 FAILED로 기록할 오류 코드와 내부 기록용 상세를 담음
public class AiCallException extends RuntimeException {

    private final ErrorCode errorCode;
    private final boolean retryable;   // 연결 실패·5xx만 재시도 (계약 7.3)

    public AiCallException(ErrorCode errorCode, String detail, boolean retryable) {
        super(detail);
        this.errorCode = errorCode;
        this.retryable = retryable;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }

    public boolean isRetryable() {
        return retryable;
    }
}
