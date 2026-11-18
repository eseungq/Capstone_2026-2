package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.inspection.dto.AcknowledgeRequest;
import com.capstone.inspection.inspection.dto.RecheckListItem;
import com.capstone.inspection.inspection.dto.RecheckRequest;
import com.capstone.inspection.inspection.dto.RecheckResponse;
import com.capstone.inspection.inspection.dto.RecheckSummaryResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// AUTO_PASS 표본 재확인 (계약 6.11). 권한은 SecurityConfig: 제출 WORKER, 목록 WORKER·ADMIN, /admin/** ADMIN
@Tag(name = "표본 재확인", description = "AUTO_PASS 건 일부를 다시 확인. 시스템 판정은 바꾸지 않고 결과만 따로 저장")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class RecheckController {

    private final RecheckService recheckService;

    @Operation(summary = "재확인 목록", description = "status=PENDING(기본)·DONE, DONE에서 result(PASS·FAIL)·acknowledged 필터, "
            + "partCode 필터, 뽑힌 순서. REVIEW 대기열과 따로 셈. 확인 안 된 FAIL만: status=DONE&result=FAIL&acknowledged=false")
    @GetMapping("/rechecks")
    public ApiResponse<PageResponse<RecheckListItem>> list(
            @RequestParam(defaultValue = "PENDING") RecheckService.Status status,
            @RequestParam(required = false) Judgement result,
            @RequestParam(required = false) Boolean acknowledged,
            @RequestParam(required = false) String partCode,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.of(recheckService.list(status, result, acknowledged, partCode, page, size));
    }

    @Operation(summary = "재확인 결과", description = "WORKER만. 표본으로 뽑힌 AUTO_PASS 건의 재확인 결과(PASS·FAIL) 기록. "
            + "원래 판정(PASS·SYSTEM)은 바뀌지 않음. 같은 값 재전송 200, 다른 값 409 ALREADY_RECHECKED, 표본이 아니면 409 NOT_RECHECKABLE")
    @PostMapping("/inspections/{inspectionId}/recheck")
    public ApiResponse<RecheckResponse> recheck(@AuthenticationPrincipal AuthUser user,
                                                @PathVariable String inspectionId,
                                                @Valid @RequestBody RecheckRequest request) {
        return ApiResponse.of(recheckService.recheck(user, inspectionId, request));
    }

    @Operation(summary = "재확인 FAIL 확인함", description = "ADMIN만. 재확인 결과가 FAIL인 건에 관리자가 봤다는 기록을 남김 "
            + "(문제 해결 완료가 아님). 이미 확인함이면 처음 기록 그대로 200, FAIL이 아니면 409 NOT_ACKNOWLEDGEABLE")
    @PostMapping("/admin/rechecks/{inspectionId}/acknowledge")
    public ApiResponse<RecheckResponse> acknowledge(@AuthenticationPrincipal AuthUser user,
                                                    @PathVariable String inspectionId,
                                                    @Valid @RequestBody(required = false) AcknowledgeRequest request) {
        return ApiResponse.of(recheckService.acknowledge(user, inspectionId, request == null ? null : request.note()));
    }

    @Operation(summary = "재확인 요약", description = "ADMIN만. 기간(receivedAt) 안 AUTO_PASS의 추출 규칙별 구간 집계, 결정 누락, "
            + "대기·완료(대기는 정상·불량으로 세지 않음), 비교 비율(compare*Rate, 셋 다 주거나 생략), REVIEW·재확인 대기 시간과 화면 체류 시간")
    @GetMapping("/admin/rechecks/summary")
    public ApiResponse<RecheckSummaryResponse> summary(
            @RequestParam(required = false) String partCode,
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(required = false) Double compareNearRate,
            @RequestParam(required = false) Double compareMidRate,
            @RequestParam(required = false) Double compareLowRate) {
        return ApiResponse.of(recheckService.summary(partCode, Times.parseParam("from", from),
                Times.parseParam("to", to), compareRule(compareNearRate, compareMidRate, compareLowRate)));
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
}
