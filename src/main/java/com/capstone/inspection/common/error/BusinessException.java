package com.capstone.inspection.common.error;

// 서비스 계층에서 던지는 예외. GlobalExceptionHandler가 ErrorCode에 맞춰 응답으로 바꿈
public class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;
    private final String inspectionId; // 검사와 연결된 오류일 때만 값 (예: AI 분석 실패)

    public BusinessException(ErrorCode errorCode) {
        this(errorCode, errorCode.getDefaultMessage(), null);
    }

    public BusinessException(ErrorCode errorCode, String message) {
        this(errorCode, message, null);
    }

    public BusinessException(ErrorCode errorCode, String message, String inspectionId) {
        super(message);
        this.errorCode = errorCode;
        this.inspectionId = inspectionId;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }

    public String getInspectionId() {
        return inspectionId;
    }
}
