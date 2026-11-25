package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.ScreenTiming;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;
import com.capstone.inspection.domain.inspection.WorkerConfirmationRepository;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.dto.ConfirmRequest;
import com.capstone.inspection.inspection.dto.ConfirmResponse;
import com.capstone.inspection.inspection.dto.ScreenTimings;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Optional;

// 작업자 확인 (계약 v4 6.7). REVIEW_PENDING 건에 작업자 최종 판정을 기록
//   - AI 결과·정책 결과는 그대로 두고 worker_confirmation 1건 + inspection의 final_judgement·judged_by만 기록
//   - 같은 값 재전송은 기존 결과(200), 다른 값은 409 ALREADY_CONFIRMED. 화면 체류 시간(선택)은 처음 저장한 값 유지
//   - 동시 제출: 조건부 갱신(final_judgement IS NULL) + worker_confirmation.inspection_id UNIQUE로 1건만 저장.
//     진 쪽은 저장 트랜잭션을 롤백하고, 새 트랜잭션에서 이긴 쪽 결과를 읽어 재전송 규칙대로 응답
@Service
public class InspectionConfirmService {

    private static final Logger log = LoggerFactory.getLogger(InspectionConfirmService.class);

    private final InspectionRepository inspectionRepository;
    private final WorkerConfirmationRepository confirmationRepository;
    private final UserRepository userRepository;
    private final TransactionTemplate tx;
    private final TransactionTemplate readTx;

    public InspectionConfirmService(InspectionRepository inspectionRepository,
                                    WorkerConfirmationRepository confirmationRepository,
                                    UserRepository userRepository,
                                    PlatformTransactionManager txManager) {
        this.inspectionRepository = inspectionRepository;
        this.confirmationRepository = confirmationRepository;
        this.userRepository = userRepository;
        this.tx = new TransactionTemplate(txManager);
        this.readTx = new TransactionTemplate(txManager);
        this.readTx.setReadOnly(true);
    }

    // 다른 요청이 먼저 판정을 기록한 경우 (저장 트랜잭션 롤백용)
    private static final class LostRace extends RuntimeException {
        LostRace() {
            super(null, null, false, false);
        }
    }

    // 1건 처리 결과. saved = 이번 요청으로 저장했는지 (false면 재전송 규칙으로 기존 기록을 돌려준 것)
    public record Outcome(ConfirmResponse response, boolean saved) {
    }

    public ConfirmResponse confirm(AuthUser worker, String inspectionId, ConfirmRequest request) {
        ScreenTiming timing = ScreenTimings.of(request.screenDwellMs(), request.firstOpenedAt(), request.openCount());
        return confirmOne(worker, inspectionId, request.finalJudgement(), request.comment(), timing, null).response();
    }

    // 6.7 규칙으로 1건 처리. 건마다 자기 트랜잭션이라 일괄 FAIL(6.7.1)도 건별로 이걸 호출 (호출하는 쪽에 트랜잭션을 두지 말 것)
    //   batchId: 일괄 요청이면 그 묶음 ID, 단건이면 null. 처음 저장할 때만 기록
    public Outcome confirmOne(AuthUser worker, String inspectionId, Judgement judgement, String comment,
                              ScreenTiming timing, String batchId) {
        String normalized = comment == null || comment.isBlank() ? null : comment.trim();
        try {
            return tx.execute(status -> save(worker, inspectionId, judgement, normalized, timing, batchId));
        } catch (LostRace | DataIntegrityViolationException e) {
            log.info("동시 확인 요청: 먼저 저장된 판정 기준으로 응답 {}", inspectionId);
            return new Outcome(readTx.execute(status -> replayExisting(inspectionId, judgement)), false);
        }
    }

    // 지금 저장된 판정 (일괄 FAIL 실패 결과에 현재 값을 채우는 용도). 확인 기록이 있으면 그 값, 없으면 검사의 값
    public Optional<ConfirmResponse> current(String inspectionId) {
        return readTx.execute(status -> inspectionRepository.findDetailById(inspectionId).map(i ->
                confirmationRepository.findByInspectionIdWithWorker(inspectionId)
                        .map(c -> ConfirmResponse.of(i, c))
                        .orElseGet(() -> new ConfirmResponse(i.getId(), i.getInspectionNo(), i.getPredictedQuality(),
                                i.getRecommendedAction(), i.getFinalJudgement(), i.getJudgedBy(), null, null))));
    }

    private Outcome save(AuthUser worker, String inspectionId, Judgement judgement, String comment,
                         ScreenTiming timing, String batchId) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));

        // 이미 확인된 건: 재전송 규칙
        WorkerConfirmation existing = confirmationRepository.findByInspectionIdWithWorker(inspectionId).orElse(null);
        if (existing != null) {
            return new Outcome(replay(i, existing, judgement), false);
        }
        if (DisplayState.of(i) != DisplayState.REVIEW_PENDING) {
            throw new BusinessException(ErrorCode.NOT_REVIEWABLE); // AUTO_PASS·FAILED·분석 중
        }

        if (inspectionRepository.markWorkerJudgement(inspectionId, judgement) != 1) {
            throw new LostRace();
        }
        WorkerConfirmation saved = confirmationRepository.saveAndFlush(
                new WorkerConfirmation(i, userRepository.getReferenceById(worker.userId()), judgement, comment, timing,
                        batchId));
        log.info("작업자 확인 {} {} {} by={} batch={}", i.getInspectionNo(), i.getId(), judgement, worker.loginId(), batchId);
        return new Outcome(new ConfirmResponse(i.getId(), i.getInspectionNo(), i.getPredictedQuality(),
                i.getRecommendedAction(), judgement, JudgedBy.WORKER, worker.loginId(),
                Times.toOffset(saved.getConfirmedAt())), true);
    }

    private ConfirmResponse replayExisting(String inspectionId, Judgement judgement) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        WorkerConfirmation existing = confirmationRepository.findByInspectionIdWithWorker(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_REVIEWABLE));
        return replay(i, existing, judgement);
    }

    private static ConfirmResponse replay(Inspection i, WorkerConfirmation existing, Judgement judgement) {
        if (existing.getFinalJudgement() != judgement) {
            throw new BusinessException(ErrorCode.ALREADY_CONFIRMED);
        }
        return ConfirmResponse.of(i, existing);
    }
}
