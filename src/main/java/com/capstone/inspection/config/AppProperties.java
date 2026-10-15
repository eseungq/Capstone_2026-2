package com.capstone.inspection.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

// application.yml의 app.* 값을 묶어 두는 설정 객체
// 미확정(TBD) 값은 전부 여기로 모아 코드 수정 없이 바꿀 수 있게 함
@ConfigurationProperties(prefix = "app")
public record AppProperties(Upload upload, Ai ai, Storage storage, Auth auth, Inspection inspection) {

    // 업로드 제한 (TBD-08)
    public record Upload(List<String> allowedContentTypes, long maxBytes, int minWidth, int minHeight) {
    }

    // AI 서버 호출 설정 (TBD-01, TBD-09)
    public record Ai(String baseUrl, int connectTimeoutMs, int readTimeoutMs, int retryCount,
                     boolean imageSizeCheckEnabled) {
    }

    // 이미지 저장소 설정 (TBD-01)
    public record Storage(String type, String localRoot, int accessUrlTtlSeconds, String publicBaseUrl) {
    }

    // 인증 설정 (TBD-10)
    public record Auth(String jwtSecret, long accessTokenTtlSeconds, long refreshTokenTtlSeconds,
                       int loginLockThreshold) {
    }

    // 비동기 분석 스레드 풀 (계약 5장)
    public record Inspection(int analysisPoolSize, int analysisQueueCapacity) {
    }
}
