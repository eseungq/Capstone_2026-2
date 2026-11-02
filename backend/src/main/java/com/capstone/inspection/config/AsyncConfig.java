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
    public static final String PUSH_EXECUTOR = "pushExecutor";
    private static final int PUSH_QUEUE_CAPACITY = 200;

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
        executor.setTaskDecorator(AsyncConfig::withMdc);
        executor.initialize();
        return executor;
    }

    // 푸시 발송 전용 (계약 v4 8장): 분석 스레드를 잡지 않게 분리. 알림은 순서대로 1개 스레드에서 보냄
    @Bean(name = PUSH_EXECUTOR)
    public ThreadPoolTaskExecutor pushExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(PUSH_QUEUE_CAPACITY);
        executor.setThreadNamePrefix("push-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        executor.setTaskDecorator(AsyncConfig::withMdc);
        executor.initialize();
        return executor;
    }

    // 요청의 traceId 등 MDC 값을 작업 스레드로 넘김
    private static Runnable withMdc(Runnable task) {
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
    }
}
