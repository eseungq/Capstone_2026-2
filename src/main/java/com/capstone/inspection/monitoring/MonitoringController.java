package com.capstone.inspection.monitoring;

import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.monitoring.dto.PartMonitoringResponse;
import com.capstone.inspection.monitoring.dto.QueueResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@Tag(name = "모니터링", description = "부품별 최근 상태·확인 필요 목록")
@RestController
@RequestMapping("/api/v1/monitoring")
@RequiredArgsConstructor
public class MonitoringController {

    private final MonitoringService monitoringService;

    @Operation(summary = "부품별 모니터링", description = "WORKER·ADMIN. 부품별 모델·정책 상태, 마지막 접수 시각, "
            + "확인 필요·오류(재검사 안 한 FAILED) 건수, 최근 검사(최신순)")
    @GetMapping("/parts")
    public ApiResponse<List<PartMonitoringResponse>> parts() {
        return ApiResponse.of(monitoringService.parts());
    }

    @Operation(summary = "확인 필요 목록", description = "WORKER·ADMIN. REVIEW_PENDING과 재검사하지 않은 FAILED를 오래된 순으로. "
            + "다음 페이지는 응답의 nextCursor를 cursor로 전달 (null이면 마지막), size 최대 100")
    @GetMapping("/queue")
    public ApiResponse<QueueResponse> queue(@RequestParam(defaultValue = "ALL") QueueType type,
                                            @RequestParam(required = false) String partCode,
                                            @RequestParam(required = false) String cursor,
                                            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.of(monitoringService.queue(type, partCode, cursor, size));
    }
}
