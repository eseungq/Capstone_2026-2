package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository.AutoPassDecision;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshot;
import com.capstone.inspection.domain.inspection.RecheckRuleSnapshotRepository;
import com.capstone.inspection.domain.inspection.ScreenTiming;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.dto.RecheckBlock;
import com.capstone.inspection.inspection.dto.RecheckListItem;
import com.capstone.inspection.inspection.dto.RecheckRequest;
import com.capstone.inspection.inspection.dto.RecheckResponse;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse;
import com.capstone.inspection.inspection.dto.ScreenTimings;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import com.capstone.inspection.common.time.Times;

// AUTO_PASS 표본 재확인 (계약 6.11). 작업자 확인(6.7)과 같은 재전송·동시 제출 규칙
//   - 재확인 결과는 auto_pass_recheck에만 기록. inspection의 시스템 판정(PASS·SYSTEM)은 바꾸지 않음
//   - 같은 값 재전송은 기존 결과(200, 화면 체류 시간도 처음 값), 다른 값은 409 ALREADY_RECHECKED
//   - 동시 제출: 조건부 갱신(result IS NULL)으로 1건만 기록. 진 쪽은 이긴 쪽 결과로 재전송 규칙 적용
//   - 관리자 확인함: 재확인 FAIL만. 해결 완료가 아니라 관리자가 봤다는 기록. 다시 보내면 처음 기록 그대로
@Service
public class RecheckService {

    private static final Logger log = LoggerFactory.getLogger(RecheckService.class);

    public enum Status { PENDING, DONE }

    private final AutoPassRecheckRepository recheckRepository;
    private final InspectionRepository inspectionRepository;
    private final UserRepository userRepository;
    private final PartRepository partRepository;
    private final RecheckRuleSnapshotRepository ruleRepository;
    private final TransactionTemplate tx;
    private final TransactionTemplate readTx;

    public RecheckService(AutoPassRecheckRepository recheckRepository, InspectionRepository inspectionRepository,
                          UserRepository userRepository, PartRepository partRepository,
                          RecheckRuleSnapshotRepository ruleRepository, PlatformTransactionManager txManager) {
        this.recheckRepository = recheckRepository;
        this.inspectionRepository = inspectionRepository;
        this.userRepository = userRepository;
        this.partRepository = partRepository;
        this.ruleRepository = ruleRepository;
        this.tx = new TransactionTemplate(txManager);
        this.readTx = new TransactionTemplate(txManager);
        this.readTx.setReadOnly(true);
    }

    public RecheckResponse recheck(AuthUser worker, String inspectionId, RecheckRequest request) {
        String comment = trimToNull(request.comment());
        ScreenTiming timing = ScreenTimings.of(request.screenDwellMs(), request.firstOpenedAt(), request.openCount());
        RecheckResponse saved = tx.execute(status -> save(worker, inspectionId, request.result(), comment, timing));
        return saved != null ? saved : readTx.execute(status -> replay(inspectionId, request.result()));
    }

    // 기록했으면 응답, 다른 요청이 먼저 기록했으면 null
    private RecheckResponse save(AuthUser worker, String inspectionId, Judgement result, String comment,
                                 ScreenTiming timing) {
        Inspection i = inspectionRepository.findById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        AutoPassRecheck r = recheckRepository.findSampledByInspectionIdWithUser(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_RECHECKABLE)); // 표본이 아님
        if (r.getResult() != null) {
            return replayed(i, r, result);
        }
        LocalDateTime at = Times.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        if (recheckRepository.markResult(inspectionId, result, comment,
                userRepository.getReferenceById(worker.userId()), at,
                timing == null ? null : timing.getScreenDwellMs(), timing == null ? null : timing.getFirstOpenedAt(),
                timing == null ? null : timing.getOpenCount()) != 1) {
            return null;
        }
        log.info("표본 재확인 {} {} {} by={}", i.getInspectionNo(), i.getId(), result, worker.loginId());
        return response(i, recheckRepository.findSampledByInspectionIdWithUser(inspectionId).orElseThrow());
    }

    // 관리자 확인함 (계약 6.11). 재확인 FAIL만, 이미 확인했으면 처음 기록 그대로 200
    //   동시 요청: 조건부 갱신(acknowledged_at IS NULL)으로 1건만 기록. 진 쪽은 새 트랜잭션에서 이긴 쪽 기록을 읽음
    //   (같은 트랜잭션에서 다시 읽으면 MySQL 반복 읽기 스냅샷 때문에 확인 전 상태가 보일 수 있음)
    public RecheckResponse acknowledge(AuthUser admin, String inspectionId, String note) {
        String trimmed = trimToNull(note);
        RecheckResponse saved = tx.execute(status -> markAcknowledged(admin, inspectionId, trimmed));
        return saved != null ? saved : readTx.execute(status -> currentRecheck(inspectionId));
    }

    // 기록했거나 이미 확인돼 있으면 응답, 다른 요청이 먼저 기록했으면 null
    private RecheckResponse markAcknowledged(AuthUser admin, String inspectionId, String note) {
        Inspection i = inspectionRepository.findById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        AutoPassRecheck r = recheckRepository.findSampledByInspectionIdWithUser(inspectionId)
                .filter(found -> found.getResult() == Judgement.FAIL)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_ACKNOWLEDGEABLE));
        if (r.getAcknowledgedAt() != null) {
            return response(i, r);
        }
        LocalDateTime at = Times.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        if (recheckRepository.markAcknowledged(inspectionId, userRepository.getReferenceById(admin.userId()),
                at, note) != 1) {
            return null;
        }
        log.info("재확인 FAIL 확인함 {} {} by={}", i.getInspectionNo(), i.getId(), admin.loginId());
        return response(i, recheckRepository.findSampledByInspectionIdWithUser(inspectionId).orElseThrow());
    }

    private RecheckResponse currentRecheck(String inspectionId) {
        Inspection i = inspectionRepository.findById(inspectionId).orElseThrow();
        return response(i, recheckRepository.findSampledByInspectionIdWithUser(inspectionId).orElseThrow());
    }

    private static String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private RecheckResponse replay(String inspectionId, Judgement result) {
        Inspection i = inspectionRepository.findById(inspectionId).orElseThrow();
        return replayed(i, recheckRepository.findSampledByInspectionIdWithUser(inspectionId).orElseThrow(), result);
    }

    private static RecheckResponse replayed(Inspection i, AutoPassRecheck r, Judgement result) {
        if (r.getResult() != result) {
            throw new BusinessException(ErrorCode.ALREADY_RECHECKED);
        }
        return response(i, r);
    }

    private static RecheckResponse response(Inspection i, AutoPassRecheck r) {
        return new RecheckResponse(i.getId(), i.getInspectionNo(), i.getFinalJudgement(), i.getJudgedBy(),
                RecheckBlock.of(r));
    }

    // 요약 (계약 6.11): 기간 안 AUTO_PASS의 규칙별 구간 집계·누락·대기 시간·체류 시간
    //   compare*Rate: 같은 기록으로 다시 셀 가상 비교 비율 (셋 다 주거나 모두 생략)
    public RecheckSummaryResponse summary(String partCode, LocalDateTime from, LocalDateTime to,
                                          Double compareNearRate, Double compareMidRate, Double compareLowRate) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "from은 to보다 늦을 수 없습니다.");
        }
        RecheckRule compareRule = compareRule(compareNearRate, compareMidRate, compareLowRate);
        String code = partCode == null || partCode.isBlank() ? null : partCode.trim();
        return readTx.execute(s -> {
            if (code != null && partRepository.findByPartCode(code).isEmpty()) {
                throw new BusinessException(ErrorCode.INVALID_PART_CODE);
            }
            List<AutoPassDecision> decisions = recheckRepository.findAutoPassDecisions(code, from, to);
            Set<String> ruleIds = new HashSet<>();
            decisions.forEach(d -> {
                if (d.inspectionRuleId() != null) {
                    ruleIds.add(d.inspectionRuleId());
                }
                if (d.decisionRuleId() != null) {
                    ruleIds.add(d.decisionRuleId());
                }
            });
            Map<String, RecheckRuleSnapshot> rules = ruleRepository.findAllById(ruleIds).stream()
                    .collect(Collectors.toMap(RecheckRuleSnapshot::getId, Function.identity()));
            return RecheckSummary.build(code, from, to, decisions, recheckRepository.findReviewTimings(code, from, to),
                    rules, compareRule);
        });
    }

    // 비교 비율 → 규칙 (경계는 쓰지 않으므로 0). 셋 다 없으면 null, 일부만·범위 밖이면 400
    private static RecheckRule compareRule(Double near, Double mid, Double low) {
        if (near == null && mid == null && low == null) {
            return null;
        }
        for (Double rate : new Double[]{near, mid, low}) {
            if (rate == null || !Double.isFinite(rate) || rate < 0 || rate > 1) {
                throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                        "compareNearRate·compareMidRate·compareLowRate는 셋 다 0~1로 주거나 모두 생략해야 합니다.");
            }
        }
        return new RecheckRule(0, 0, near, mid, low);
    }

    // 재확인 목록: 뽑힌 순서 (먼저 뽑힌 건부터 확인). result·acknowledged는 완료 목록에서만
    public PageResponse<RecheckListItem> list(Status status, Judgement result, Boolean acknowledged, String partCode,
                                              int page, int size) {
        if (page < 0 || size < 1 || size > InspectionQueryService.MAX_PAGE_SIZE) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "page는 0 이상, size는 1~" + InspectionQueryService.MAX_PAGE_SIZE + "이어야 합니다.");
        }
        if (status != Status.DONE && (result != null || acknowledged != null)) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "result·acknowledged는 status=DONE에서만 쓸 수 있습니다.");
        }
        String code = partCode == null || partCode.isBlank() ? null : partCode.trim();
        return readTx.execute(s -> {
            if (code != null && partRepository.findByPartCode(code).isEmpty()) {
                throw new BusinessException(ErrorCode.INVALID_PART_CODE);
            }
            return PageResponse.of(recheckRepository.search(status == Status.DONE, code, result, acknowledged,
                            PageRequest.of(page, size)),
                    rows -> rows.stream().map(RecheckListItem::of).toList());
        });
    }
}
