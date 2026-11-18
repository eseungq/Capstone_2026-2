package com.capstone.inspection.inspection;

import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

// AUTO_PASS가 확정된 뒤 표본 재확인 대상으로 뽑을지 결정 (계약 6.11)
//   판정 저장과 별도 트랜잭션이라 여기서 실패해도 AUTO_PASS 결과에는 영향 없음 (호출 쪽에서 예외를 삼키고 로그만)
//   실패한 건은 결정 행이 없으므로 RecheckSweeper가 다시 호출. 같은 검사는 항상 같은 결정이라 다시 해도 결과 같음
@Component
@RequiredArgsConstructor
public class RecheckSampler {

    private static final Logger log = LoggerFactory.getLogger(RecheckSampler.class);

    private final InspectionRepository inspectionRepository;
    private final AutoPassRecheckRepository recheckRepository;
    private final AppProperties props;

    @Transactional
    public void sampleIfNeeded(String inspectionId) {
        AppProperties.Recheck config = props.recheck();
        if (config == null || !config.enabled()) {
            return;
        }
        Inspection i = inspectionRepository.findById(inspectionId).orElse(null);
        if (i == null || i.getRecommendedAction() != RecommendedAction.AUTO_PASS || i.getJudgedBy() != JudgedBy.SYSTEM
                || i.getCalibratedDefectProbability() == null || i.getPassThresholdApplied() == null
                || recheckRepository.existsByInspectionId(inspectionId)) {
            return;
        }
        RecheckRules.Decision d = RecheckRules.decide(i.getId(), i.getCalibratedDefectProbability(),
                i.getPassThresholdApplied(), config);
        double rate = Math.round(d.rate() * 1_000_000) / 1_000_000.0; // DB DECIMAL(7,6)
        // 뽑히지 않은 결정도 남김: 행이 없는 AUTO_PASS는 저장 실패로 보고 RecheckSweeper가 다시 처리
        recheckRepository.save(new AutoPassRecheck(i, d.sampled(), d.stratum(), rate));
        if (d.sampled()) {
            log.info("표본 재확인 대상 {} {} stratum={} rate={}", i.getInspectionNo(), i.getId(), d.stratum(), rate);
        }
    }
}
