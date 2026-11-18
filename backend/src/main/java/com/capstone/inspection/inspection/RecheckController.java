package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.inspection.dto.RecheckListItem;
import com.capstone.inspection.inspection.dto.RecheckRequest;
import com.capstone.inspection.inspection.dto.RecheckResponse;
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

// AUTO_PASS 표본 재확인 (계약 6.11). 권한은 SecurityConfig: 제출 WORKER, 목록 WORKER·ADMIN
@Tag(name = "표본 재확인", description = "AUTO_PASS 건 일부를 다시 확인. 시스템 판정은 바꾸지 않고 결과만 따로 저장")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class RecheckController {

    private final RecheckService recheckService;

    @Operation(summary = "재확인 목록", description = "status=PENDING(기본)·DONE, partCode 필터, 뽑힌 순서. REVIEW 대기열과 따로 셈")
    @GetMapping("/rechecks")
    public ApiResponse<PageResponse<RecheckListItem>> list(
            @RequestParam(defaultValue = "PENDING") RecheckService.Status status,
            @RequestParam(required = false) String partCode,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.of(recheckService.list(status, partCode, page, size));
    }

    @Operation(summary = "재확인 결과", description = "WORKER만. 표본으로 뽑힌 AUTO_PASS 건의 재확인 결과(PASS·FAIL) 기록. "
            + "원래 판정(PASS·SYSTEM)은 바뀌지 않음. 같은 값 재전송 200, 다른 값 409 ALREADY_RECHECKED, 표본이 아니면 409 NOT_RECHECKABLE")
    @PostMapping("/inspections/{inspectionId}/recheck")
    public ApiResponse<RecheckResponse> recheck(@AuthenticationPrincipal AuthUser user,
                                                @PathVariable String inspectionId,
                                                @Valid @RequestBody RecheckRequest request) {
        return ApiResponse.of(recheckService.recheck(user, inspectionId, request));
    }
}
