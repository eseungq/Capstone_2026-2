package com.capstone.inspection.inspection;

import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshot;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshotRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

// 지금 적용 중인 표본 재확인 규칙 (계약 6.11). 설정(app.recheck.*)은 실행 중 바뀌지 않으므로 처음 한 번 찾거나 만들고 id를 기억
//   판정 트랜잭션 안에서 불려도 규칙 행은 별도 트랜잭션으로 만들어, 다른 서버와 동시에 만들 때의 UNIQUE 충돌이 판정에 번지지 않음
@Component
public class RecheckRuleRegistry {

    private static final Logger log = LoggerFactory.getLogger(RecheckRuleRegistry.class);

    private final AppProperties props;
    private final RecheckRuleSnapshotRepository repository;
    private final TransactionTemplate newTx;
    private volatile String currentId;

    public RecheckRuleRegistry(AppProperties props, RecheckRuleSnapshotRepository repository,
                               PlatformTransactionManager txManager) {
        this.props = props;
        this.repository = repository;
        this.newTx = new TransactionTemplate(txManager);
        this.newTx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    // 판정 중인 검사에 연결할 규칙 (호출한 트랜잭션의 참조). 기능이 꺼져 있으면 null → 그 AUTO_PASS는 추출 대상이 아님
    //   규칙 행 조회·생성이 실패해도 AUTO_PASS 판정에는 영향 없도록 null (그 건은 규칙 없는 결정 누락으로 남음, 계약 6.11)
    public RecheckRuleSnapshot currentRuleReference() {
        try {
            String id = currentRuleId();
            return id == null ? null : repository.getReferenceById(id);
        } catch (RuntimeException e) {
            log.warn("표본 재확인 규칙을 찾지 못해 이 판정에는 규칙을 남기지 않음: {}", e.toString());
            return null;
        }
    }

    String currentRuleId() {
        AppProperties.Recheck config = props.recheck();
        if (config == null || !config.enabled()) {
            return null;
        }
        String id = currentId;
        if (id == null) {
            id = findOrCreate(config.rule(), config.trialName());
            currentId = id;
        }
        return id;
    }

    private String findOrCreate(RecheckRule rule, String trialName) {
        try {
            return newTx.execute(s -> repository.findByVersionAndTrial(rule.version(), trialName)
                    .orElseGet(() -> repository.saveAndFlush(new RecheckRuleSnapshot(rule, trialName))).getId());
        } catch (DataIntegrityViolationException e) { // 다른 서버가 먼저 만듦
            return newTx.execute(s -> repository.findByVersionAndTrial(rule.version(), trialName).orElseThrow().getId());
        }
    }
}
