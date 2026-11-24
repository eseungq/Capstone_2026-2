package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.ScreenTiming;
import com.capstone.inspection.inspection.dto.ConfirmBatchRequest;
import com.capstone.inspection.inspection.dto.ConfirmBatchResponse;
import com.capstone.inspection.inspection.dto.ConfirmBatchResponse.Outcome;
import com.capstone.inspection.inspection.dto.ConfirmBatchResponse.Result;
import com.capstone.inspection.inspection.dto.ConfirmResponse;
import com.capstone.inspection.inspection.dto.ScreenTimings;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

// 일괄 FAIL (계약 v4 6.7.1). 작업자가 직접 고른 REVIEW 건을 한 번에 FAIL로 확정
//   - 요청 값 오류(FAIL 아님·건수·중복 ID·체류 시간)는 저장 전에 전부 확인해 요청 전체를 400으로 거절
//   - 건마다 6.7 단건 확인(InspectionConfirmService.confirmOne)을 그대로 호출. 판정 규칙·동시 제출 보장은 거기 한 곳에만 있음
//   - 건마다 자기 트랜잭션이라 한 건이 실패해도 앞뒤 건은 저장된 채 남음. 그래서 이 클래스에는 트랜잭션을 두지 않음
@Service
public class InspectionConfirmBatchService {

    private static final Logger log = LoggerFactory.getLogger(InspectionConfirmBatchService.class);

    private final InspectionConfirmService confirmService;

    public InspectionConfirmBatchService(InspectionConfirmService confirmService) {
        this.confirmService = confirmService;
    }

    public ConfirmBatchResponse confirmBatch(AuthUser worker, ConfirmBatchRequest request) {
        if (request.finalJudgement() != Judgement.FAIL) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "일괄 확인은 finalJudgement=FAIL만 허용합니다.");
        }
        List<ConfirmBatchRequest.Item> items = request.items();
        rejectDuplicates(items);
        // 체류 시간 오류도 저장 전에 확인 (한 건이라도 틀리면 전체 400)
        List<ScreenTiming> timings = items.stream()
                .map(it -> ScreenTimings.of(it.screenDwellMs(), it.firstOpenedAt(), it.openCount()))
                .toList();

        String batchId = UUID.randomUUID().toString();
        List<Result> results = new ArrayList<>(items.size());
        for (int n = 0; n < items.size(); n++) {
            results.add(confirmItem(worker, items.get(n).inspectionId(), request.comment(), timings.get(n), batchId));
        }
        log.info("일괄 FAIL batch={} by={} 요청 {}건, 저장 {}건", batchId, worker.loginId(), items.size(),
                results.stream().filter(r -> r.result() == Outcome.CONFIRMED).count());
        return new ConfirmBatchResponse(batchId, results);
    }

    private static void rejectDuplicates(List<ConfirmBatchRequest.Item> items) {
        Set<String> seen = new HashSet<>();
        for (ConfirmBatchRequest.Item item : items) {
            if (!seen.add(item.inspectionId())) {
                throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                        "같은 inspectionId가 두 번 있습니다: " + item.inspectionId());
            }
        }
    }

    private Result confirmItem(AuthUser worker, String inspectionId, String comment, ScreenTiming timing,
                               String batchId) {
        try {
            InspectionConfirmService.Outcome outcome =
                    confirmService.confirmOne(worker, inspectionId, Judgement.FAIL, comment, timing, batchId);
            return Result.of(inspectionId, outcome.saved() ? Outcome.CONFIRMED : Outcome.ALREADY_CONFIRMED,
                    outcome.response(), null);
        } catch (BusinessException e) {
            return failed(inspectionId, outcomeOf(e.getErrorCode()), e.getErrorCode());
        } catch (RuntimeException e) {
            // DB·잠금 오류 등: 그 건만 실패로 돌려주고 나머지는 계속 처리 (그 건의 트랜잭션은 이미 롤백됨)
            log.error("일괄 FAIL 중 오류 batch={} inspection={}", batchId, inspectionId, e);
            return failed(inspectionId, Outcome.ERROR, ErrorCode.INTERNAL_SERVER_ERROR);
        }
    }

    // 6.7 단건 오류 코드 → 건별 결과
    private static Outcome outcomeOf(ErrorCode code) {
        return switch (code) {
            case ALREADY_CONFIRMED -> Outcome.CONFLICT;
            case NOT_REVIEWABLE -> Outcome.NOT_REVIEWABLE;
            case INSPECTION_NOT_FOUND -> Outcome.NOT_FOUND;
            default -> Outcome.ERROR;
        };
    }

    // 실패 결과에 현재 값 채우기. 조회까지 실패하면 ID와 오류 코드만
    private Result failed(String inspectionId, Outcome outcome, ErrorCode errorCode) {
        ConfirmResponse current = null;
        if (outcome != Outcome.NOT_FOUND) {
            try {
                current = confirmService.current(inspectionId).orElse(null);
            } catch (RuntimeException e) {
                log.warn("일괄 FAIL 결과의 현재 값 조회 실패 inspection={}", inspectionId, e);
            }
        }
        return Result.of(inspectionId, outcome, current, errorCode);
    }
}
