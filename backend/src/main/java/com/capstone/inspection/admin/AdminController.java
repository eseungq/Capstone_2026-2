package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.ModelResponse;
import com.capstone.inspection.admin.dto.PolicyCreateRequest;
import com.capstone.inspection.admin.dto.PolicyResponse;
import com.capstone.inspection.admin.dto.ThresholdRequest;
import com.capstone.inspection.admin.dto.UserLockResponse;
import com.capstone.inspection.common.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

// ADMIN만 호출 가능 (SecurityConfig)
@Tag(name = "관리자", description = "모델 조회, 자동 통과 정책 등록·조정·적용·중지, 계정 잠금 해제")
@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class AdminController {

    private final AdminPolicyService policyService;
    private final AdminUserService userService;

    @Operation(summary = "모델 목록", description = "모델 버전·부품·보정기·활성 여부와 AI 서버 로드 가능 여부(확인 불가·확인 끔이면 null). 조회만 제공")
    @GetMapping("/models")
    public ApiResponse<List<ModelResponse>> models() {
        return ApiResponse.of(policyService.models());
    }

    @Operation(summary = "정책 목록", description = "partCode·active 필터, 최신 생성순")
    @GetMapping("/policies")
    public ApiResponse<List<PolicyResponse>> policies(@RequestParam(required = false) String partCode,
                                                      @RequestParam(required = false) Boolean active) {
        return ApiResponse.of(policyService.policies(partCode, active));
    }

    @Operation(summary = "정책 등록", description = "AI 검증 자료 등록. ready는 규칙으로 결정, active=false로 시작")
    @PostMapping("/policies")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<PolicyResponse> create(@Valid @RequestBody PolicyCreateRequest request) {
        return ApiResponse.of(policyService.create(request));
    }

    @Operation(summary = "기준치 조정", description = "검증 범위 안에서만 가능. 기존 정책은 그대로 두고 새 버전을 만듦 (active=false)")
    @PostMapping("/policies/{id}/threshold")
    @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<PolicyResponse> threshold(@PathVariable String id, @Valid @RequestBody ThresholdRequest request) {
        return ApiResponse.of(policyService.adjustThreshold(id, request.passThreshold()));
    }

    @Operation(summary = "정책 적용", description = "ready이고 모델이 active이며 보정기가 일치할 때만. 같은 모델의 다른 정책은 자동 중지")
    @PostMapping("/policies/{id}/activate")
    public ApiResponse<PolicyResponse> activate(@PathVariable String id) {
        return ApiResponse.of(policyService.activate(id));
    }

    @Operation(summary = "정책 중지")
    @PostMapping("/policies/{id}/deactivate")
    public ApiResponse<PolicyResponse> deactivate(@PathVariable String id) {
        return ApiResponse.of(policyService.deactivate(id));
    }

    @Operation(summary = "계정 잠금 해제", description = "로그인 실패 누적으로 잠긴 계정을 풀고 실패 횟수 초기화. 잠기지 않은 계정도 200")
    @PostMapping("/users/{loginId}/unlock")
    public ApiResponse<UserLockResponse> unlock(@PathVariable String loginId) {
        return ApiResponse.of(userService.unlock(loginId));
    }
}
