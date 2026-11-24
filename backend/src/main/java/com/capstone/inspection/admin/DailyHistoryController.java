package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.DailyDetailResponse;
import com.capstone.inspection.admin.dto.DailyHistoryRow;
import com.capstone.inspection.common.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

// ADMIN만 호출 가능 (SecurityConfig의 /admin/**). 필수 값도 서비스에서 확인해 400 INVALID_PARAMETER 메시지를 맞춤
@Tag(name = "관리자")
@RestController
@RequestMapping("/api/v1/admin/automation")
@RequiredArgsConstructor
public class DailyHistoryController {

    private final DailyHistoryService dailyService;

    @Operation(summary = "날짜별 이력",
            description = "부품의 KST 날짜(from ≤ 날짜 < to, 최대 " + DailyHistoryService.MAX_DAYS + "일)별, "
                    + "판정 당시 정책·모델·보정기 조합별 건수. 최신 날짜부터. total = autoPass + autoFail + review.total "
                    + "(수동 전환은 manual, 분석 실패는 failed로 따로). 판정 확인 요청은 처리된 것만 confirmedOpposite, "
                    + "대기는 openRequests. 표본 재확인 결과는 넣지 않음")
    @GetMapping("/daily")
    public ApiResponse<List<DailyHistoryRow>> daily(@RequestParam(required = false) String partCode,
                                                    @RequestParam(required = false) String from,
                                                    @RequestParam(required = false) String to) {
        return ApiResponse.of(dailyService.daily(partCode, from, to));
    }

    @Operation(summary = "기준 상세",
            description = "날짜 행 하나(같은 날짜·정책)의 기준 주변 REVIEW. passBand: GOOD 예측, 통과 기준 < 확률 ≤ 통과 기준 + band. "
                    + "failBand: DEFECT 예측, 불량 기준 − band ≤ 확률 < 불량 기준 (불량 기준이 없으면 null). "
                    + "band 0.001~0.5, 기본 0.05. reference는 자료가 없어 null")
    @GetMapping("/daily/detail")
    public ApiResponse<DailyDetailResponse> detail(@RequestParam(required = false) String partCode,
                                                   @RequestParam(required = false) String date,
                                                   @RequestParam(required = false) String policyId,
                                                   @RequestParam(defaultValue = "" + DailyHistoryService.DEFAULT_BAND)
                                                   double band) {
        return ApiResponse.of(dailyService.detail(partCode, date, policyId, band));
    }
}
