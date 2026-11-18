package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.PolicySimulationResponse;
import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.common.time.Times;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// ADMIN만 호출 가능 (SecurityConfig의 /admin/**)
@Tag(name = "관리자")
@RestController
@RequestMapping("/api/v1/admin")
@RequiredArgsConstructor
public class PolicySimulationController {

    private final PolicySimulationService simulationService;

    @Operation(summary = "정책 후보 비교",
            description = "정책과 같은 모델·보정기의 분석 완료 건에 현재 기준치와 후보 기준치를 대입해 판정이 바뀌는 건수와 "
                    + "그중 작업자 PASS·FAIL·미확인을 셈. current도 과거 실제 판정이 아니라 현재 기준치로 다시 계산한 값. "
                    + "AUTO_PASS(PASS·SYSTEM)는 실제 라벨이 아니라 미확인. 조회만 함. 기간을 주지 않으면 전체 기간")
    @GetMapping("/policies/{id}/simulation")
    public ApiResponse<PolicySimulationResponse> simulate(@PathVariable String id,
                                                          @RequestParam double candidateThreshold,
                                                          @RequestParam(required = false) String from,
                                                          @RequestParam(required = false) String to) {
        return ApiResponse.of(simulationService.simulate(id, candidateThreshold, Times.parseParam("from", from),
                Times.parseParam("to", to)));
    }
}
