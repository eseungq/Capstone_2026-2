package com.capstone.inspection.inspection;

import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;

// 추출 결정이 저장되지 않은 AUTO_PASS를 다시 처리 (계약 6.11)
//   분석 직후 추출(RecheckSampler)이 실패하면 결정 행이 없음 → 주기적으로 찾아 다시 결정
//   - 방금 끝난 건은 분석 스레드가 아직 추출 중일 수 있어 SETTLE만큼 지난 건부터
//   - 결정은 판정 때 검사에 남긴 규칙으로 함 (지금 설정이 아님). 규칙이 없는 건은 대상이 아님 → 요약에서 누락으로 셈
//   - 계속 실패하는 건을 끝없이 다시 시도하지 않도록 완료 후 LOOKBACK(1일) 안의 건만
//   - 같은 검사가 동시에 처리돼도 inspection_id UNIQUE로 1건만 남음
@Component
@RequiredArgsConstructor
public class RecheckSweeper {

    private static final Logger log = LoggerFactory.getLogger(RecheckSweeper.class);

    static final Duration SETTLE = Duration.ofMinutes(1);
    static final Duration LOOKBACK = Duration.ofDays(1);
    private static final int BATCH_SIZE = 100;

    private final AutoPassRecheckRepository recheckRepository;
    private final RecheckSampler sampler;
    private final AppProperties props;

    // 스케줄은 SchedulingConfig(app.recheck.sweep-enabled)로 켬. 테스트는 sweep()을 직접 호출
    @Scheduled(initialDelayString = "${app.recheck.sweep-initial-delay-ms:60000}",
            fixedDelayString = "${app.recheck.sweep-delay-ms:300000}")
    public void scheduledSweep() {
        sweep();
    }

    // 다시 결정한 건수
    public int sweep() {
        AppProperties.Recheck config = props.recheck();
        if (config == null || !config.enabled()) {
            return 0;
        }
        LocalDateTime now = LocalDateTime.now();
        List<String> ids = recheckRepository.findUndecidedAutoPass(now.minus(LOOKBACK), now.minus(SETTLE),
                PageRequest.of(0, BATCH_SIZE));
        int done = 0;
        for (String id : ids) {
            try {
                sampler.sampleIfNeeded(id);
                done++;
            } catch (RuntimeException e) {
                log.warn("표본 재확인 추출 재처리 실패 {}: {}", id, e.toString());
            }
        }
        if (!ids.isEmpty()) {
            log.info("표본 재확인 추출 재처리: 대상 {}건, 처리 {}건", ids.size(), done);
        }
        return done;
    }
}
