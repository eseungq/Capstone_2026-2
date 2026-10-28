package com.capstone.inspection.common.error;

import com.capstone.inspection.common.api.ErrorResponse;
import com.capstone.inspection.common.trace.TraceIdFilter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.support.MissingServletRequestPartException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

// 모든 예외를 공통 오류 형식으로 바꾸는 곳 (FR-BE-10)
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    // 서비스에서 의도적으로 던진 예외
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException e) {
        ErrorCode code = e.getErrorCode();
        // 분석 실패 오류이고 검사 ID가 있으면 status=FAILED를 함께 내려 줌
        String status = (code.isAnalysisFailure() && e.getInspectionId() != null) ? "FAILED" : null;
        log.warn("business error: {} {}", code, e.getMessage());
        return build(code, e.getMessage(), e.getInspectionId(), status);
    }

    // @Valid 검증 실패, 필수 파라미터·파트 누락, 형식 오류, JSON 파싱 실패
    @ExceptionHandler({BindException.class, MissingServletRequestParameterException.class,
            MissingServletRequestPartException.class, MethodArgumentTypeMismatchException.class,
            HttpMessageNotReadableException.class})
    public ResponseEntity<ErrorResponse> handleInvalid(Exception e) {
        log.warn("invalid request: {}", e.getMessage());
        return build(ErrorCode.INVALID_PARAMETER, ErrorCode.INVALID_PARAMETER.getDefaultMessage(), null, null);
    }

    // 스프링 multipart 한도 초과 (spring.servlet.multipart.max-file-size)
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ErrorResponse> handleTooLarge(MaxUploadSizeExceededException e) {
        return build(ErrorCode.IMAGE_TOO_LARGE, ErrorCode.IMAGE_TOO_LARGE.getDefaultMessage(), null, null);
    }

    // 없는 경로
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(NoResourceFoundException e) {
        return build(ErrorCode.NOT_FOUND, ErrorCode.NOT_FOUND.getDefaultMessage(), null, null);
    }

    // 지원하지 않는 HTTP 메서드
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ErrorResponse> handleMethod(HttpRequestMethodNotSupportedException e) {
        return build(ErrorCode.METHOD_NOT_ALLOWED, ErrorCode.METHOD_NOT_ALLOWED.getDefaultMessage(), null, null);
    }

    // 예상하지 못한 오류: 상세 내용은 로그에만 남기고 앱에는 traceId만 전달
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
        log.error("unexpected error", e);
        return build(ErrorCode.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_SERVER_ERROR.getDefaultMessage(), null, null);
    }

    private ResponseEntity<ErrorResponse> build(ErrorCode code, String message, String inspectionId, String status) {
        String traceId = MDC.get(TraceIdFilter.MDC_KEY); // 요청마다 발급한 추적 ID
        ErrorResponse body = ErrorResponse.of(code.name(), message, traceId, inspectionId, status);
        return ResponseEntity.status(code.getStatus()).body(body);
    }
}
