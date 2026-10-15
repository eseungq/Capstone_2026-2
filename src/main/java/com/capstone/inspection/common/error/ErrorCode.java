package com.capstone.inspection.common.error;

import org.springframework.http.HttpStatus;

// 명세서 5.7 오류 코드표
// analysisFailure = true 인 코드는 검사를 FAILED로 기록한 경우에 사용
public enum ErrorCode {

    // 400 입력 오류
    INVALID_PARAMETER(HttpStatus.BAD_REQUEST, "요청 값이 올바르지 않습니다.", false),
    INVALID_PART_CODE(HttpStatus.BAD_REQUEST, "존재하지 않는 부품 코드입니다.", false),
    INVALID_INSPECTION_ITEM(HttpStatus.BAD_REQUEST, "해당 부품에 없는 검사항목입니다.", false),
    INVALID_IMAGE_FORMAT(HttpStatus.BAD_REQUEST, "지원하지 않는 이미지 형식이거나 이미지를 읽을 수 없습니다.", false),
    IMAGE_RESOLUTION_TOO_LOW(HttpStatus.BAD_REQUEST, "이미지 해상도가 기준보다 낮습니다.", false),
    IMAGE_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, "이미지 용량이 기준을 초과했습니다.", false),
    POLICY_THRESHOLD_OUT_OF_RANGE(HttpStatus.BAD_REQUEST, "검증 범위를 벗어난 기준치입니다.", false),

    // 401·403·423 인증·권한
    AUTH_INVALID_CREDENTIALS(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다.", false),
    AUTH_TOKEN_EXPIRED(HttpStatus.UNAUTHORIZED, "로그인이 만료되었습니다. 토큰을 재발급하세요.", false),
    AUTH_TOKEN_INVALID(HttpStatus.UNAUTHORIZED, "유효하지 않은 토큰입니다.", false),
    AUTH_ACCOUNT_LOCKED(HttpStatus.LOCKED, "로그인 실패가 누적되어 계정이 잠겼습니다.", false),
    ACCESS_DENIED(HttpStatus.FORBIDDEN, "접근 권한이 없습니다.", false),

    // 404·405 대상 없음
    INSPECTION_NOT_FOUND(HttpStatus.NOT_FOUND, "검사를 찾을 수 없습니다.", false),
    POLICY_NOT_FOUND(HttpStatus.NOT_FOUND, "정책을 찾을 수 없습니다.", false),
    IMAGE_NOT_AVAILABLE(HttpStatus.NOT_FOUND, "이미지를 찾을 수 없거나 접근 기간이 지났습니다.", false),
    NOT_FOUND(HttpStatus.NOT_FOUND, "요청한 경로가 없습니다.", false),                      // 5.7 표에 추가 필요
    METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "지원하지 않는 요청 방식입니다.", false), // 5.7 표에 추가 필요

    // 409 상태 충돌
    NOT_REVIEWABLE(HttpStatus.CONFLICT, "작업자 확인 대상이 아닌 검사입니다.", false),
    ALREADY_CONFIRMED(HttpStatus.CONFLICT, "이미 다른 판정으로 확인된 검사입니다.", false),
    POLICY_NOT_READY(HttpStatus.CONFLICT, "사용할 수 없는 정책 또는 모델입니다.", false),
    NOT_RETRYABLE(HttpStatus.CONFLICT, "분석 실패(FAILED) 검사만 재검사할 수 있습니다.", false),
    ALREADY_RETRIED(HttpStatus.CONFLICT, "이미 재검사한 검사입니다.", false),

    // 422 모델 없음
    MODEL_NOT_AVAILABLE(HttpStatus.UNPROCESSABLE_ENTITY, "해당 부품의 사용 가능한 모델이 없습니다.", false),
    IDEMPOTENCY_KEY_MISMATCH(HttpStatus.UNPROCESSABLE_ENTITY, "같은 Idempotency-Key로 다른 요청이 들어왔습니다.", false),

    // 500 서버 오류
    STORAGE_UPLOAD_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "원본 이미지 저장에 실패했습니다.", false),
    INTERNAL_SERVER_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "서버 오류가 발생했습니다.", false),

    // 502·504 AI 분석 실패 (검사는 FAILED로 기록)
    AI_SERVER_ERROR(HttpStatus.BAD_GATEWAY, "AI 분석에 실패했습니다. 다시 검사해 주세요.", true),
    AI_RESPONSE_INVALID(HttpStatus.BAD_GATEWAY, "AI 분석 결과가 올바르지 않습니다. 다시 검사해 주세요.", true),
    AI_REQUEST_REJECTED(HttpStatus.BAD_GATEWAY, "AI 서버가 분석 요청을 거절했습니다.", true),
    AI_SERVER_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT, "AI 분석 시간이 초과되었습니다. 다시 검사해 주세요.", true);

    private final HttpStatus status;         // HTTP 상태 코드
    private final String defaultMessage;     // 앱에 보여 줄 기본 문구
    private final boolean analysisFailure;   // 검사 FAILED와 연결되는 오류인지

    ErrorCode(HttpStatus status, String defaultMessage, boolean analysisFailure) {
        this.status = status;
        this.defaultMessage = defaultMessage;
        this.analysisFailure = analysisFailure;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getDefaultMessage() {
        return defaultMessage;
    }

    public boolean isAnalysisFailure() {
        return analysisFailure;
    }
}
