package com.capstone.inspection.inspection;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;
import com.capstone.inspection.domain.inspection.WorkerConfirmationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

// 검사 기록 CSV 내보내기 (ADMIN, 보고서·엑셀용). 조건은 검사 이력과 같고 접수 시각 오름차순
// 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM + CRLF. 이미지·AI 응답 원문·오류 상세는 넣지 않음
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InspectionExportService {

    public static final int MAX_ROWS = 10_000;
    private static final Sort EXPORT_SORT = Sort.by(Sort.Order.asc("receivedAt"), Sort.Order.asc("id"));
    // 초가 0이어도 생략하지 않고 소수점 이하는 버림 (엑셀에서 같은 열의 형식이 섞이지 않게)
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ssXXX");
    private static final byte[] BOM = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
    private static final List<String> HEADER = List.of("inspectionNo", "partCode", "lineCode", "source",
            "originInspectionNo", "displayState", "status", "receivedAt", "completedAt", "modelVersion",
            "calibratorVersion", "predictedQuality", "rawDefectProbability", "calibratedDefectProbability",
            "inferenceTimeMs", "policyVersion", "passThresholdApplied", "recommendedAction", "reviewReason",
            "finalJudgement", "judgedBy", "workerLoginId", "confirmedAt", "errorCode");

    private final InspectionQueryService queryService;
    private final InspectionRepository inspectionRepository;
    private final WorkerConfirmationRepository confirmationRepository;

    public byte[] exportCsv(String partCode, DisplayState displayState, ReviewMismatch mismatch,
                            LocalDateTime from, LocalDateTime to) {
        Specification<Inspection> filter = queryService.filter(partCode, displayState, mismatch, from, to);
        long count = inspectionRepository.count(filter);
        if (count > MAX_ROWS) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "한 번에 " + MAX_ROWS + "건까지 내보낼 수 있습니다. 기간을 줄여 주세요. (대상 " + count + "건)");
        }
        List<Inspection> inspections = inspectionRepository.findAll(
                InspectionSpecs.fetchPart().and(InspectionSpecs.fetchModelAndPolicy()).and(filter), EXPORT_SORT);

        List<String> ids = inspections.stream().map(Inspection::getId).toList();
        Map<String, WorkerConfirmation> confirmations = ids.isEmpty() ? Map.of()
                : confirmationRepository.findByInspectionIdsWithWorker(ids).stream()
                .collect(Collectors.toMap(c -> c.getInspection().getId(), Function.identity()));
        // 재검사·수동 판정의 원래 FAILED 검사 번호 (기간 밖일 수 있어 따로 조회)
        List<String> originIds = inspections.stream().map(Inspection::getRetryOfInspectionId)
                .filter(Objects::nonNull).distinct().toList();
        Map<String, String> originNos = originIds.isEmpty() ? Map.of()
                : inspectionRepository.findAllById(originIds).stream()
                .collect(Collectors.toMap(Inspection::getId, Inspection::getInspectionNo));

        StringBuilder csv = new StringBuilder();
        appendRow(csv, HEADER);
        for (Inspection i : inspections) {
            // 일반 검사는 원본 ID가 null (Map.of()는 get(null)에서 NPE)
            String originNo = i.getRetryOfInspectionId() == null ? null : originNos.get(i.getRetryOfInspectionId());
            appendRow(csv, row(i, confirmations.get(i.getId()), originNo));
        }
        byte[] body = csv.toString().getBytes(StandardCharsets.UTF_8);
        byte[] result = Arrays.copyOf(BOM, BOM.length + body.length);
        System.arraycopy(body, 0, result, BOM.length, body.length);
        return result;
    }

    private static List<String> row(Inspection i, WorkerConfirmation confirmation, String originNo) {
        // 수동 판정은 AI 결과가 없으므로 모델·점수 칸을 비움 (상세 API의 ai: null과 같음)
        boolean ai = !i.isManual();
        List<String> row = new ArrayList<>(HEADER.size());
        row.add(i.getInspectionNo());
        row.add(i.getPart().getPartCode());
        row.add(i.getLineCode());
        row.add(text(i.getSource()));
        row.add(originNo);
        row.add(text(DisplayState.of(i)));
        row.add(text(i.getStatus()));
        row.add(time(i.getReceivedAt()));
        row.add(time(i.getCompletedAt()));
        row.add(ai ? i.getModel().getModelVersion() : null);
        row.add(ai ? i.getCalibratorVersion() : null);
        row.add(ai ? text(i.getPredictedQuality()) : null);
        row.add(ai ? number(i.getRawDefectProbability()) : null);
        row.add(ai ? number(i.getCalibratedDefectProbability()) : null);
        row.add(ai ? text(i.getInferenceTimeMs()) : null);
        row.add(i.getPolicy() != null ? i.getPolicy().getPolicyVersion() : null);
        row.add(number(i.getPassThresholdApplied()));
        row.add(text(i.getRecommendedAction()));
        row.add(text(i.getReviewReason()));
        row.add(text(i.getFinalJudgement()));
        row.add(text(i.getJudgedBy()));
        row.add(confirmation != null ? confirmation.getWorker().getLoginId() : null);
        row.add(confirmation != null ? time(confirmation.getConfirmedAt()) : null);
        row.add(InspectionQueryService.errorCodeOf(i));
        return row;
    }

    private static String text(Object value) {
        return value == null ? null : value.toString();
    }

    private static String time(LocalDateTime value) {
        return value == null ? null : Times.toOffset(value).format(TIME_FORMAT);
    }

    // 0.008761이 8.761E-3으로 나오지 않게
    private static String number(Double value) {
        return value == null ? null : BigDecimal.valueOf(value).toPlainString();
    }

    private static void appendRow(StringBuilder csv, List<String> cells) {
        for (int c = 0; c < cells.size(); c++) {
            if (c > 0) {
                csv.append(',');
            }
            csv.append(cell(cells.get(c)));
        }
        csv.append("\r\n");
    }

    // RFC 4180 따옴표 처리 + 엑셀 수식 실행 방지 (=, +, -, @로 시작하면 앞에 ')
    static String cell(String value) {
        if (value == null || value.isEmpty()) {
            return "";
        }
        String v = "=+-@\t\r".indexOf(value.charAt(0)) >= 0 ? "'" + value : value;
        if (v.contains(",") || v.contains("\"") || v.contains("\n") || v.contains("\r")) {
            return "\"" + v.replace("\"", "\"\"") + "\"";
        }
        return v;
    }
}
