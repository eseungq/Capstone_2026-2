package com.capstone.inspection.config;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.Map;

// 비동기 분석용 스레드 풀 (계약 v4 5장). 풀 크기 = AI 동시 호출 수
@Configuration
public class AsyncConfig {

    public static final String ANALYSIS_EXECUTOR = "inspectionAnalysisExecutor";

    @Bean(name = ANALYSIS_EXECUTOR)
    public ThreadPoolTaskExecutor inspectionAnalysisExecutor(AppProperties props) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(props.inspection().analysisPoolSize());
        executor.setMaxPoolSize(props.inspection().analysisPoolSize());
        executor.setQueueCapacity(props.inspection().analysisQueueCapacity());
        executor.setThreadNamePrefix("analysis-");
        // 종료 시 진행 중 분석은 마무리하도록 대기 (남은 RECEIVED 건은 재시작 시 다시 처리)
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        // 접수 요청의 traceId 등 MDC 값을 분석 스레드로 넘김
        executor.setTaskDecorator(task -> {
            Map<String, String> context = MDC.getCopyOfContextMap();
            return () -> {
                if (context != null) {
                    MDC.setContextMap(context);
                }
                try {
                    task.run();
                } finally {
                    MDC.clear();
                }
            };
        });
        executor.initialize();
        return executor;
    }
}
