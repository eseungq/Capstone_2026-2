package com.capstone.inspection.common.api;

// 성공 응답 공통 형식: { "data": ... } (명세서 5.1)
public record ApiResponse<T>(T data) {

    public static <T> ApiResponse<T> of(T data) {
        return new ApiResponse<>(data);
    }
}
