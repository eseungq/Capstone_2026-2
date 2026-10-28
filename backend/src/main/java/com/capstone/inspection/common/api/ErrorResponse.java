package com.capstone.inspection.common.api;

import com.fasterxml.jackson.annotation.JsonInclude;

// 오류 응답 공통 형식: { "error": { code, message, traceId, inspectionId?, status? } } (명세서 5.1)
public record ErrorResponse(Body error) {

    // inspectionId와 status는 분석 실패(FAILED)처럼 검사와 연결된 오류에만 포함
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Body(String code, String message, String traceId, String inspectionId, String status) {
    }

    public static ErrorResponse of(String code, String message, String traceId,
                                   String inspectionId, String status) {
        return new ErrorResponse(new Body(code, message, traceId, inspectionId, status));
    }
}
