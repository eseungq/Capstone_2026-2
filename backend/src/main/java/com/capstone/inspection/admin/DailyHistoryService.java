package com.capstone.inspection.admin;

import com.capstone.inspection.admin.DailyHistory.RequestSummary;
import com.capstone.inspection.admin.dto.DailyDetailResponse;
import com.capstone.inspection.admin.dto.DailyHistoryRow;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionRepository.DailyInspection;
import com.capstone.inspection.domain.inspection.JudgementRequestRepository;
import com.capstone.inspection.domain.model.AutomationPolicy;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

// 관리자 날짜별 이력·기준 상세 (계약 6.13). 조회만 함
//   한 부품·기간의 검사와 판정 확인 요청을 필요한 값만 한 번씩 읽고(정책은 ID로 한 번) 집계는 DailyHistory·DailyBands
//   날짜는 KST: 범위 경계(KST 0시)를 저장 시각으로 바꿔 조회하고, 행의 날짜도 KST로 셈
@Service
@RequiredArgsConstructor
public class DailyHistoryService {

    static final int MAX_DAYS = 92;
    static final double DEFAULT_BAND = 0.05;
    private static final double MIN_BAND = 0.001;
    private static final double MAX_BAND = 0.5;

    private final PartRepository partRepository;
    private final InspectionRepository inspectionRepository;
    private final JudgementRequestRepository requestRepository;
    private final AutomationPolicyRepository policyRepository;

    @Transactional(readOnly = true)
    public List<DailyHistoryRow> daily(String partCode, String fromParam, String toParam) {
        String code = required("partCode", partCode);
        LocalDate from = requiredDate("from", fromParam);
        LocalDate to = requiredDate("to", toParam);
        if (!from.isBefore(to) || ChronoUnit.DAYS.between(from, to) > MAX_DAYS) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "from은 to보다 앞서야 하고 기간은 최대 " + MAX_DAYS + "일입니다.");
        }
        Part part = part(code);
        LocalDateTime start = Times.kstStartOfDay(from);
        LocalDateTime end = Times.kstStartOfDay(to);
        List<DailyInspection> inspections = inspectionRepository.findDaily(part.getId(), start, end);
        return DailyHistory.rows(inspections, policiesOf(inspections), requests(part, start, end));
    }

    @Transactional(readOnly = true)
    public DailyDetailResponse detail(String partCode, String dateParam, String policyId, double band) {
        String code = required("partCode", partCode);
        LocalDate date = requiredDate("date", dateParam);
        String id = required("policyId", policyId);
        if (!(band >= MIN_BAND && band <= MAX_BAND)) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "band는 " + MIN_BAND + "~" + MAX_BAND + " 사이여야 합니다.");
        }
        Part part = part(code);
        // 다른 부품의 정책도 이 부품 기준으로는 없는 정책
        AutomationPolicy policy = policyRepository.findById(id)
                .filter(p -> p.getItem().getPart().getId().equals(part.getId()))
                .orElseThrow(() -> new BusinessException(ErrorCode.POLICY_NOT_FOUND));
        LocalDateTime start = Times.kstStartOfDay(date);
        LocalDateTime end = Times.kstStartOfDay(date.plusDays(1));
        List<DailyInspection> rows = inspectionRepository.findDaily(part.getId(), start, end).stream()
                .filter(i -> id.equals(i.policyId()))
                .toList();
        Map<String, RequestSummary> requests = requests(part, start, end);
        return new DailyDetailResponse(date, part.getPartCode(), policy.getId(), policy.getPolicyVersion(),
                policy.getModel().getModelVersion(), policy.getCalibratorVersion(), policy.getPassThreshold(),
                policy.getFailThreshold(), policy.isAutoFailEnabled(), band,
                policy.getPassThreshold() != null
                        ? DailyBands.passBand(rows, policy.getPassThreshold(), band, requests) : null,
                policy.getFailThreshold() != null
                        ? DailyBands.failBand(rows, policy.getFailThreshold(), band, requests) : null,
                null);
    }

    private Map<String, AutomationPolicy> policiesOf(List<DailyInspection> inspections) {
        List<String> ids = inspections.stream().map(DailyInspection::policyId).filter(Objects::nonNull)
                .distinct().toList();
        return ids.isEmpty() ? Map.of() : policyRepository.findAllById(ids).stream()
                .collect(Collectors.toUnmodifiableMap(AutomationPolicy::getId, Function.identity()));
    }

    private Map<String, RequestSummary> requests(Part part, LocalDateTime start, LocalDateTime end) {
        return DailyHistory.summarize(requestRepository.findFactsByPartAndReceived(part.getId(), start, end));
    }

    private Part part(String code) {
        return partRepository.findByPartCode(code)
                .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_PART_CODE));
    }

    private static String required(String name, String value) {
        if (value == null || value.isBlank()) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, name + "은(는) 필수입니다.");
        }
        return value.trim();
    }

    private static LocalDate requiredDate(String name, String value) {
        return Times.parseDateParam(name, required(name, value));
    }
}
