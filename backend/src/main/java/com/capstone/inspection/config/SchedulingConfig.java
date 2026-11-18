package com.capstone.inspection.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

// 주기 작업: 표본 재확인 추출 재처리(RecheckSweeper). 통합 테스트는 끄고 직접 호출 (데이터 정리와 겹치지 않게)
@Configuration
@EnableScheduling
@ConditionalOnProperty(name = "app.recheck.sweep-enabled", havingValue = "true", matchIfMissing = true)
public class SchedulingConfig {
}
