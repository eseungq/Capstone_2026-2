package com.capstone.inspection;

import com.capstone.inspection.config.AppProperties;

import java.util.List;

// 단위 테스트용 설정값 (application.yml 기본값과 같게)
public final class TestProps {

    private TestProps() {
    }

    public static AppProperties defaults() {
        return new AppProperties(
                new AppProperties.Upload(List.of("image/jpeg", "image/png"), 20_971_520L, 0, 0),
                new AppProperties.Ai("http://localhost:8090", 2000, 10000, 1, false, 50_000_000),
                new AppProperties.Storage("local", "./build/test-storage", 600, "http://localhost:8080"),
                new AppProperties.Auth("test-secret-key-for-unit-tests-32-bytes-or-more", 1800, 1209600, 5),
                new AppProperties.Inspection(2, 500),
                new AppProperties.Monitoring(10));
    }
}
