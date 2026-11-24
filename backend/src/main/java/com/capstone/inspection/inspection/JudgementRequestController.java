package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.inspection.dto.JudgementRequestCreate;
import com.capstone.inspection.inspection.dto.JudgementRequestResponse;
import com.capstone.inspection.inspection.dto.JudgementResolveRequest;
import com.capstone.inspection.inspection.dto.JudgementResolveResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// 판정 확인 요청·정정 (계약 6.12). 권한은 SecurityConfig: 요청 WORKER, /admin/** ADMIN
@Tag(name = "판정 확인 요청", description = "시스템 판정 건을 작업자가 다르게 확인하면 요청, 관리자가 유지·정정. 최초 판정은 바꾸지 않음")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class JudgementRequestController {

    private final JudgementRequestService requestService;

    @Operation(summary = "판정 확인 요청", description = "WORKER만. judgedBy = SYSTEM 건만(아니면 409 NOT_REQUESTABLE). "
            + "claimedJudgement는 현재 판정(정정됐으면 정정 판정)과 달라야 함(같으면 400). 검사당 대기 요청 1건: "
            + "같은 작업자·같은 판정 재전송은 기존 요청 200, 그 밖에는 409 REQUEST_ALREADY_OPEN")
    @PostMapping("/inspections/{inspectionId}/judgement-requests")
    public ResponseEntity<ApiResponse<JudgementRequestResponse>> create(@AuthenticationPrincipal AuthUser user,
                                                                        @PathVariable String inspectionId,
                                                                        @Valid @RequestBody JudgementRequestCreate request) {
        JudgementRequestService.Created result = requestService.create(user, inspectionId, request);
        HttpStatus status = result.created() ? HttpStatus.CREATED : HttpStatus.OK;
        return ResponseEntity.status(status).body(ApiResponse.of(result.request()));
    }

    @Operation(summary = "판정 확인 요청 목록", description = "ADMIN만. status=OPEN(기본, 오래된 요청부터)·RESOLVED(KEPT+CORRECTED)·ALL "
            + "(최근 처리·요청부터), partCode 필터, page(0부터)·size(기본 20, 최대 100)")
    @GetMapping("/admin/judgement-requests")
    public ApiResponse<PageResponse<JudgementRequestResponse>> list(
            @RequestParam(defaultValue = "OPEN") JudgementRequestService.ListStatus status,
            @RequestParam(required = false) String partCode,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.of(requestService.list(status, partCode, page, size));
    }

    @Operation(summary = "판정 확인 요청 처리", description = "ADMIN만. decision=KEEP(유지)·CORRECT(요청한 판정으로 정정), note 필수. "
            + "응답은 요청 1건과 검사의 correction. 이미 처리된 요청에 같은 결정 200(처음 기록), 다른 결정 409 REQUEST_ALREADY_RESOLVED")
    @PostMapping("/admin/judgement-requests/{requestId}/resolve")
    public ApiResponse<JudgementResolveResponse> resolve(@AuthenticationPrincipal AuthUser user,
                                                         @PathVariable String requestId,
                                                         @Valid @RequestBody JudgementResolveRequest request) {
        return ApiResponse.of(requestService.resolve(user, requestId, request.decision(), request.note()));
    }
}
