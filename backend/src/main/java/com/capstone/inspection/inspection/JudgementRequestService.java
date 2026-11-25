package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.JudgementRequest;
import com.capstone.inspection.domain.inspection.JudgementRequestRepository;
import com.capstone.inspection.domain.inspection.JudgementRequestStatus;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.dto.CorrectionBlock;
import com.capstone.inspection.inspection.dto.JudgementRequestCreate;
import com.capstone.inspection.inspection.dto.JudgementRequestResponse;
import com.capstone.inspection.inspection.dto.JudgementResolveRequest.Decision;
import com.capstone.inspection.inspection.dto.JudgementResolveResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.EnumSet;
import java.util.List;
import com.capstone.inspection.common.time.Times;

// 판정 확인 요청·정정 (계약 6.12). 표본 재확인(6.11)과는 별도 기록
//   - 대상은 시스템 판정(judgedBy = SYSTEM) 건만. 최초 판정(inspection.final_judgement·judged_by)은 바꾸지 않음
//   - 현재 판정 = 마지막 CORRECTED 요청의 판정, 없으면 최초 판정. 요청 판정은 현재 판정과 달라야 함
//   - 검사당 대기 요청 1건: 같은 작업자·같은 판정 재전송은 기존 요청(200), 그 밖에는 409 REQUEST_ALREADY_OPEN
//     동시 요청은 DB UNIQUE(open_key)로 1건만 저장. 진 쪽은 새 트랜잭션에서 이긴 쪽 요청으로 같은 규칙 적용
//   - 처리: 조건부 갱신(status = OPEN)으로 1건만 기록. 진 쪽은 새 트랜잭션에서 이긴 쪽 기록을 읽음
//     (같은 트랜잭션에서 다시 읽으면 MySQL 반복 읽기 스냅샷 때문에 처리 전 상태가 보일 수 있음)
@Service
public class JudgementRequestService {

    private static final Logger log = LoggerFactory.getLogger(JudgementRequestService.class);

    // 관리자 목록 상태 필터. RESOLVED = KEPT + CORRECTED
    public enum ListStatus { OPEN, RESOLVED, ALL }

    // 요청 결과. created = false면 기존 대기 요청을 돌려준 것 (200)
    public record Created(JudgementRequestResponse request, boolean created) {
    }

    private final JudgementRequestRepository requestRepository;
    private final InspectionRepository inspectionRepository;
    private final UserRepository userRepository;
    private final PartRepository partRepository;
    private final TransactionTemplate tx;
    private final TransactionTemplate readTx;

    public JudgementRequestService(JudgementRequestRepository requestRepository,
                                   InspectionRepository inspectionRepository, UserRepository userRepository,
                                   PartRepository partRepository, PlatformTransactionManager txManager) {
        this.requestRepository = requestRepository;
        this.inspectionRepository = inspectionRepository;
        this.userRepository = userRepository;
        this.partRepository = partRepository;
        this.tx = new TransactionTemplate(txManager);
        this.readTx = new TransactionTemplate(txManager);
        this.readTx.setReadOnly(true);
    }

    public Created create(AuthUser worker, String inspectionId, JudgementRequestCreate body) {
        String area = trimToNull(body.area());
        String reason = body.reason().trim();
        try {
            return tx.execute(s -> save(worker, inspectionId, body.claimedJudgement(), area, reason));
        } catch (DataIntegrityViolationException e) {
            // 동시 요청이 먼저 대기 요청을 남김 (open_key UNIQUE). 그 요청으로 재전송 규칙 적용
            Created replayed = readTx.execute(s -> requestRepository.findOpenByInspectionId(inspectionId)
                    .map(open -> replayOpen(worker, open, body.claimedJudgement())).orElse(null));
            if (replayed == null) {
                throw e;
            }
            return replayed;
        }
    }

    private Created save(AuthUser worker, String inspectionId, Judgement claimed, String area, String reason) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        if (i.getJudgedBy() != JudgedBy.SYSTEM) {
            throw new BusinessException(ErrorCode.NOT_REQUESTABLE);
        }
        Judgement current = currentJudgement(i);
        if (claimed == current) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "claimedJudgement는 현재 판정(" + current + ")과 달라야 합니다.");
        }
        var open = requestRepository.findOpenByInspectionId(inspectionId);
        if (open.isPresent()) {
            return replayOpen(worker, open.get(), claimed);
        }
        JudgementRequest saved = requestRepository.saveAndFlush(new JudgementRequest(i,
                userRepository.getReferenceById(worker.userId()), current, claimed, area, reason));
        log.info("판정 확인 요청 {} {} {}→{} by={}", i.getInspectionNo(), i.getId(), current, claimed,
                worker.loginId());
        return new Created(JudgementRequestResponse.of(saved), true);
    }

    // 대기 요청이 있을 때: 같은 작업자·같은 판정이면 기존 요청, 아니면 409
    private static Created replayOpen(AuthUser worker, JudgementRequest open, Judgement claimed) {
        if (!open.getRequestedBy().getId().equals(worker.userId()) || open.getClaimedJudgement() != claimed) {
            throw new BusinessException(ErrorCode.REQUEST_ALREADY_OPEN);
        }
        return new Created(JudgementRequestResponse.of(open), false);
    }

    private Judgement currentJudgement(Inspection i) {
        JudgementRequest corrected = JudgementCorrections.latest(
                requestRepository.findCorrectedByInspectionIds(List.of(i.getId())));
        return corrected != null ? corrected.getClaimedJudgement() : i.getFinalJudgement();
    }

    public JudgementResolveResponse resolve(AuthUser admin, String requestId, Decision decision, String note) {
        String trimmed = note.trim();
        JudgementResolveResponse saved = tx.execute(s -> markResolved(admin, requestId, decision, trimmed));
        return saved != null ? saved : readTx.execute(s -> replayResolved(
                requestRepository.findWithDetailsById(requestId).orElseThrow(), decision));
    }

    // 기록했거나 이미 처리돼 있으면 응답, 다른 요청이 먼저 기록했으면 null
    private JudgementResolveResponse markResolved(AuthUser admin, String requestId, Decision decision, String note) {
        JudgementRequest r = requestRepository.findWithDetailsById(requestId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REQUEST_NOT_FOUND));
        if (r.getStatus() != JudgementRequestStatus.OPEN) {
            return replayResolved(r, decision);
        }
        LocalDateTime at = Times.now().truncatedTo(ChronoUnit.MICROS); // DB DATETIME(6)과 같은 정밀도
        if (requestRepository.markResolved(requestId, decision.status(),
                userRepository.getReferenceById(admin.userId()), at, note) != 1) {
            return null;
        }
        log.info("판정 확인 요청 처리 {} {} {} by={}", r.getInspection().getInspectionNo(), requestId, decision,
                admin.loginId());
        return resolved(requestRepository.findWithDetailsById(requestId).orElseThrow());
    }

    // 이미 처리된 요청: 같은 결정이면 처음 기록 그대로, 다른 결정이면 409
    private JudgementResolveResponse replayResolved(JudgementRequest r, Decision decision) {
        if (r.getStatus() != decision.status()) {
            throw new BusinessException(ErrorCode.REQUEST_ALREADY_RESOLVED);
        }
        return resolved(r);
    }

    private JudgementResolveResponse resolved(JudgementRequest r) {
        JudgementRequest corrected = JudgementCorrections.latest(
                requestRepository.findCorrectedByInspectionIds(List.of(r.getInspection().getId())));
        return new JudgementResolveResponse(JudgementRequestResponse.of(r), CorrectionBlock.of(corrected));
    }

    // 관리자 목록: OPEN은 오래된 요청부터, 그 밖에는 최근 처리·요청부터
    public PageResponse<JudgementRequestResponse> list(ListStatus status, String partCode, int page, int size) {
        if (page < 0 || size < 1 || size > InspectionQueryService.MAX_PAGE_SIZE) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "page는 0 이상, size는 1~" + InspectionQueryService.MAX_PAGE_SIZE + "이어야 합니다.");
        }
        String code = trimToNull(partCode);
        return readTx.execute(s -> {
            if (code != null && partRepository.findByPartCode(code).isEmpty()) {
                throw new BusinessException(ErrorCode.INVALID_PART_CODE);
            }
            PageRequest pageable = PageRequest.of(page, size);
            Page<JudgementRequest> found = switch (status) {
                case OPEN -> requestRepository.searchOpen(code, pageable);
                case RESOLVED -> requestRepository.searchRecent(
                        EnumSet.of(JudgementRequestStatus.KEPT, JudgementRequestStatus.CORRECTED), code, pageable);
                case ALL -> requestRepository.searchRecent(EnumSet.allOf(JudgementRequestStatus.class), code,
                        pageable);
            };
            return PageResponse.of(found, rows -> rows.stream().map(JudgementRequestResponse::of).toList());
        });
    }

    private static String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
