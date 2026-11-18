package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.AutoPassRecheckRepository;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.dto.RecheckBlock;
import com.capstone.inspection.inspection.dto.RecheckListItem;
import com.capstone.inspection.inspection.dto.RecheckRequest;
import com.capstone.inspection.inspection.dto.RecheckResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

// AUTO_PASS 표본 재확인 (계약 6.11). 작업자 확인(6.7)과 같은 재전송·동시 제출 규칙
//   - 재확인 결과는 auto_pass_recheck에만 기록. inspection의 시스템 판정(PASS·SYSTEM)은 바꾸지 않음
//   - 같은 값 재전송은 기존 결과(200), 다른 값은 409 ALREADY_RECHECKED
//   - 동시 제출: 조건부 갱신(result IS NULL)으로 1건만 기록. 진 쪽은 이긴 쪽 결과로 재전송 규칙 적용
@Service
public class RecheckService {

    private static final Logger log = LoggerFactory.getLogger(RecheckService.class);

    public enum Status { PENDING, DONE }

    private final AutoPassRecheckRepository recheckRepository;
    private final InspectionRepository inspectionRepository;
    private final UserRepository userRepository;
    private final PartRepository partRepository;
    private final TransactionTemplate tx;
    private final TransactionTemplate readTx;

    public RecheckService(AutoPassRecheckRepository recheckRepository, InspectionRepository inspectionRepository,
                          UserRepository userRepository, PartRepository partRepository,
                          PlatformTransactionManager txManager) {
        this.recheckRepository = recheckRepository;
        this.inspectionRepository = inspectionRepository;
        this.userRepository = userRepository;
        this.partRepository = partRepository;
        this.tx = new TransactionTemplate(txManager);
        this.readTx = new TransactionTemplate(txManager);
        this.readTx.setReadOnly(true);
    }

    public RecheckResponse recheck(AuthUser worker, String inspectionId, RecheckRequest request) {
        String comment = request.comment() == null || request.comment().isBlank() ? null : request.comment().trim();
        RecheckResponse saved = tx.execute(status -> save(worker, inspectionId, request.result(), comment));
        return saved != null ? saved : readTx.execute(status -> replay(inspectionId, request.result()));
    }

    // 기록했으면 응답, 다른 요청이 먼저 기록했으면 null
    private RecheckResponse save(AuthUser worker, String inspectionId, Judgement result, String comment) {
        Inspection i = inspectionRepository.findById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        AutoPassRecheck r = recheckRepository.findSampledByInspectionIdWithUser(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_RECHECKABLE)); // 표본이 아님
        if (r.getResult() != null) {
            return replayed(i, r, result);
        }
        LocalDateTime at = LocalDateTime.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        if (recheckRepository.markResult(inspectionId, result, comment,
                userRepository.getReferenceById(worker.userId()), at) != 1) {
            return null;
        }
        log.info("표본 재확인 {} {} {} by={}", i.getInspectionNo(), i.getId(), result, worker.loginId());
        return response(i, recheckRepository.findSampledByInspectionIdWithUser(inspectionId).orElseThrow());
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

    // 재확인 목록: 뽑힌 순서 (먼저 뽑힌 건부터 확인)
    public PageResponse<RecheckListItem> list(Status status, String partCode, int page, int size) {
        if (page < 0 || size < 1 || size > InspectionQueryService.MAX_PAGE_SIZE) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "page는 0 이상, size는 1~" + InspectionQueryService.MAX_PAGE_SIZE + "이어야 합니다.");
        }
        String code = partCode == null || partCode.isBlank() ? null : partCode.trim();
        return readTx.execute(s -> {
            if (code != null && partRepository.findByPartCode(code).isEmpty()) {
                throw new BusinessException(ErrorCode.INVALID_PART_CODE);
            }
            return PageResponse.of(recheckRepository.search(status == Status.DONE, code, PageRequest.of(page, size)),
                    rows -> rows.stream().map(RecheckListItem::of).toList());
        });
    }
}
