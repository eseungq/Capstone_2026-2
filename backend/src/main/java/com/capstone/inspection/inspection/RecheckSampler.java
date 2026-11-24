package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshot;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

// AUTO_PASS가 확정된 뒤 표본 재확인 대상으로 뽑을지 결정 (계약 6.11)
//   판정 저장과 별도 트랜잭션이라 여기서 실패해도 AUTO_PASS 결과에는 영향 없음 (호출 쪽에서 예외를 삼키고 로그만)
//   규칙은 지금 설정이 아니라 판정 때 검사에 남긴 규칙(inspection.recheck_rule_id)을 씀. 그래서 실패한 건을
//   RecheckSweeper가 나중에 다시 호출해도 처음과 같은 결정. 규칙이 없으면 결정하지 않음 (요약에서 누락으로 셈)
@Component
@RequiredArgsConstructor
public class RecheckSampler {

    private static final Logger log = LoggerFactory.getLogger(RecheckSampler.class);

    private final InspectionRepository inspectionRepository;
    private final AutoPassRecheckRepository recheckRepository;

    @Transactional
    public void sampleIfNeeded(String inspectionId) {
        Inspection i = inspectionRepository.findById(inspectionId).orElse(null);
        if (i == null || i.getRecommendedAction() != RecommendedAction.AUTO_PASS || i.getJudgedBy() != JudgedBy.SYSTEM
                || i.getCalibratedDefectProbability() == null || i.getPassThresholdApplied() == null
                || i.getRecheckRule() == null // 판정 당시 기능이 꺼져 있었거나 규칙을 알 수 없음 → 결정하지 않음
                || recheckRepository.existsByInspectionId(inspectionId)) {
            return;
        }
        RecheckRuleSnapshot snapshot = i.getRecheckRule();
        RecheckRules.Decision d = RecheckRules.decide(i.getId(), i.getCalibratedDefectProbability(),
                i.getPassThresholdApplied(), snapshot.toRule());
        // 뽑히지 않은 결정도 남김: 행이 없는 AUTO_PASS는 저장 실패로 보고 RecheckSweeper가 다시 처리
        recheckRepository.save(new AutoPassRecheck(i, d.sampled(), d.stratum(), d.rate(), snapshot, d.ratio(),
                d.draw()));
        if (d.sampled()) {
            log.info("표본 재확인 대상 {} {} stratum={} rate={} rule={}", i.getInspectionNo(), i.getId(), d.stratum(),
                    d.rate(), snapshot.getRuleVersion());
        }
    }
}
