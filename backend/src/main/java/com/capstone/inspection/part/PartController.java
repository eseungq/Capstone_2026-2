package com.capstone.inspection.part;

import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.part.dto.PartResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(name = "부품", description = "검사 대상 부품·검사항목 조회")
@RestController
@RequestMapping("/api/v1/parts")
@RequiredArgsConstructor
public class PartController {

    private final PartService partService;

    // WORKER·ADMIN만 호출 가능 (SecurityConfig)
    @Operation(summary = "부품·검사항목 목록", description = "부품별 검사항목과 활성 모델의 사용 가능·패치 지원 여부")
    @GetMapping
    public ApiResponse<List<PartResponse>> getParts() {
        return ApiResponse.of(partService.getParts());
    }
}
