package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.ApiResponse;
import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.inspection.dto.ConfirmRequest;
import com.capstone.inspection.inspection.dto.ConfirmResponse;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse;
import com.capstone.inspection.inspection.dto.InspectionHistoryItem;
import com.capstone.inspection.inspection.dto.InspectionReceiptResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;

@Tag(name = "검사", description = "사진 접수(비동기)·검사 이력·상세·작업자 확인·재검사")
@RestController
@RequestMapping("/api/v1/inspections")
@RequiredArgsConstructor
public class InspectionController {

    private final InspectionIntakeService intakeService;
    private final InspectionQueryService queryService;
    private final InspectionConfirmService confirmService;
    private final InspectionRetryService retryService;

    @Operation(summary = "사진 접수", description = "DEVICE(시연용 ADMIN). 원본 저장 후 202와 inspectionId를 바로 반환하고 분석은 비동기로 진행. "
            + "같은 Idempotency-Key 재전송이면 기존 검사를 200으로 반환")
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ApiResponse<InspectionReceiptResponse>> receive(
            @AuthenticationPrincipal AuthUser user,
            @RequestPart("image") MultipartFile image,
            @RequestParam String partCode,
            @RequestParam(required = false) String lineCode,
            @RequestParam(required = false) String capturedAt,
            @RequestHeader(value = "Idempotency-Key", required = false) String idempotencyKey) throws IOException {
        InspectionIntakeService.Receipt receipt = intakeService.receive(user, partCode, image.getBytes(), lineCode,
                parseTime("capturedAt", capturedAt), idempotencyKey);
        HttpStatus status = receipt.replayed() ? HttpStatus.OK : HttpStatus.ACCEPTED;
        return ResponseEntity.status(status).body(ApiResponse.of(InspectionReceiptResponse.of(receipt.inspection())));
    }

    @Operation(summary = "검사 이력", description = "WORKER·ADMIN. 전체 검사를 접수 시각 최신순으로 조회. "
            + "from·to는 오프셋 포함 ISO-8601(receivedAt 기준, from ≤ receivedAt < to), page는 0부터, size 최대 100")
    @GetMapping
    public ApiResponse<PageResponse<InspectionHistoryItem>> search(
            @RequestParam(required = false) String partCode,
            @RequestParam(required = false) DisplayState displayState,
            @RequestParam(required = false) String from,
            @RequestParam(required = false) String to,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return ApiResponse.of(queryService.search(partCode, displayState, parseTime("from", from), parseTime("to", to),
                page, size));
    }

    @Operation(summary = "검사 상세", description = "WORKER·ADMIN. 분석 중이면 displayState=ANALYZING. 이미지 주소는 만료되므로 만료 후 다시 조회")
    @GetMapping("/{inspectionId}")
    public ApiResponse<InspectionDetailResponse> getDetail(@PathVariable String inspectionId) {
        return ApiResponse.of(queryService.getDetail(inspectionId));
    }

    @Operation(summary = "작업자 확인", description = "WORKER만. REVIEW_PENDING 건의 최종 판정(PASS·FAIL) 기록. "
            + "같은 값 재전송은 기존 결과(200), 다른 값은 409 ALREADY_CONFIRMED, 확인 대상이 아니면 409 NOT_REVIEWABLE")
    @PostMapping("/{inspectionId}/confirm")
    public ApiResponse<ConfirmResponse> confirm(@AuthenticationPrincipal AuthUser user,
                                                @PathVariable String inspectionId,
                                                @Valid @RequestBody ConfirmRequest request) {
        return ApiResponse.of(confirmService.confirm(user, inspectionId, request));
    }

    @Operation(summary = "재검사", description = "WORKER·ADMIN. FAILED 건을 저장된 원본으로 다시 분석. 새 inspectionId로 202 반환(retryOf=원래 ID), "
            + "원래 FAILED 기록은 그대로. FAILED가 아니면 409 NOT_RETRYABLE, 이미 재검사했으면 409 ALREADY_RETRIED")
    @PostMapping("/{inspectionId}/retry")
    public ResponseEntity<ApiResponse<InspectionReceiptResponse>> retry(@AuthenticationPrincipal AuthUser user,
                                                                        @PathVariable String inspectionId) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(ApiResponse.of(InspectionReceiptResponse.of(retryService.retry(user, inspectionId))));
    }

    // 시각 파라미터: 오프셋 포함 ISO-8601 (예: 2026-10-16T09:00:00+09:00)
    private static LocalDateTime parseTime(String name, String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Times.toLocal(OffsetDateTime.parse(value.trim()));
        } catch (DateTimeParseException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, name + "은(는) 2026-10-16T09:00:00+09:00 형식이어야 합니다.");
        }
    }
}
