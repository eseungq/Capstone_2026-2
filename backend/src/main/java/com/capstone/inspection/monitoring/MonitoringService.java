package com.capstone.inspection.monitoring;

import com.capstone.inspection.ai.ModelAvailability;
import com.capstone.inspection.ai.ModelAvailabilityService;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionRepository.PartCount;
import com.capstone.inspection.domain.inspection.InspectionRepository.PartLastReceived;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.InspectionItemRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.inspection.DisplayState;
import com.capstone.inspection.inspection.InspectionQueryService;
import com.capstone.inspection.inspection.InspectionSpecs;
import com.capstone.inspection.inspection.InspectionThumbnails;
import com.capstone.inspection.monitoring.dto.PartMonitoringResponse;
import com.capstone.inspection.monitoring.dto.QueueItem;
import com.capstone.inspection.monitoring.dto.QueueResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

// 공정 모니터링 (계약 v4 6.3, 6.4). 목록·정렬은 완료 순서가 아니라 접수 시각(receivedAt) 기준
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MonitoringService {

    public static final int MAX_QUEUE_SIZE = 100;
    // 확인 필요 목록: 오래된 순 (먼저 들어온 사진부터 확인)
    private static final Sort QUEUE_SORT = Sort.by(Sort.Order.asc("receivedAt"), Sort.Order.asc("id"));
    // sort=PRIORITY 그룹 번호 (커서에 남김)
    private static final int PRIORITY_GROUP = 0;
    private static final int REST_GROUP = 1;
    private static final Comparator<Inspection> NEWEST_FIRST = Comparator.comparing(Inspection::getReceivedAt)
            .thenComparing(Inspection::getId).reversed();

    private final AppProperties props;
    private final PartRepository partRepository;
    private final InspectionItemRepository itemRepository;
    private final AiModelRepository aiModelRepository;
    private final ModelAvailabilityService modelAvailability;
    private final AutomationPolicyRepository policyRepository;
    private final InspectionRepository inspectionRepository;
    private final InspectionThumbnails thumbnails;

    // 부품별 요약. 부품 수와 관계없이 쿼리 수가 일정 (부품·항목·모델·정책·집계 3개·최근 ID·최근 검사·이미지)
    public List<PartMonitoringResponse> parts() {
        List<Part> parts = partRepository.findAll(Sort.by("partCode"));
        Map<String, List<String>> itemIdsByPart = itemRepository.findAllWithPart().stream()
                .collect(Collectors.groupingBy(item -> item.getPart().getId(),
                        Collectors.mapping(InspectionItem::getId, Collectors.toList())));
        Set<String> itemsWithModel = aiModelRepository.findAllActiveWithItem().stream()
                .filter(m -> modelAvailability.check(m.getModelVersion()) == ModelAvailability.AVAILABLE)
                .map(m -> m.getItem().getId()).collect(Collectors.toSet());
        Set<String> itemsWithPolicy = Set.copyOf(policyRepository.findItemIdsWithActivePolicy());

        Map<String, PartLastReceived> last = inspectionRepository.findLastReceivedByPart().stream()
                .collect(Collectors.toMap(PartLastReceived::partId, x -> x));
        Map<String, Long> pending = toMap(inspectionRepository.countReviewPendingByPart());
        Map<String, Long> failed = toMap(inspectionRepository.countFailedNotRetriedByPart());

        List<Inspection> recent = inspectionRepository.findAllById(
                inspectionRepository.findRecentIdsPerPart(props.monitoring().recentSize()));
        Map<String, String> urls = thumbnails.urlsFor(recent);
        Map<String, List<PartMonitoringResponse.Recent>> recentByPart = recent.stream()
                .sorted(NEWEST_FIRST)
                .collect(Collectors.groupingBy(i -> i.getPart().getId(), Collectors.mapping(
                        i -> new PartMonitoringResponse.Recent(i.getId(), i.getInspectionNo(), DisplayState.of(i),
                                Times.toOffset(i.getReceivedAt()), urls.get(i.getId())),
                        Collectors.toList())));

        return parts.stream().map(p -> {
            List<String> itemIds = itemIdsByPart.getOrDefault(p.getId(), List.of());
            PartLastReceived lr = last.get(p.getId());
            return new PartMonitoringResponse(p.getPartCode(), p.getName(),
                    itemIds.stream().anyMatch(itemsWithModel::contains),
                    itemIds.stream().anyMatch(itemsWithPolicy::contains),
                    lr == null ? null : Times.toOffset(lr.receivedAt()),
                    pending.getOrDefault(p.getId(), 0L), failed.getOrDefault(p.getId(), 0L),
                    recentByPart.getOrDefault(p.getId(), List.of()));
        }).toList();
    }

    // 확인 필요 목록: REVIEW_PENDING + 재검사하지 않은 FAILED, 커서 페이지
    //   기본은 오래된 순. PRIORITY는 GOOD·기준 초과 REVIEW 그룹을 먼저 읽고 모자라면 나머지 그룹을 이어 읽음 (계약 6.4)
    public QueueResponse queue(QueueType type, String partCode, PredictedQuality predictedQuality, QueueSort sort,
                               String cursor, int size) {
        if (size < 1 || size > MAX_QUEUE_SIZE) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "size는 1~" + MAX_QUEUE_SIZE + "이어야 합니다.");
        }
        QueueSort order = sort == null ? QueueSort.RECEIVED : sort;
        QueueCursor after = cursor == null || cursor.isBlank() ? null : QueueCursor.decode(cursor.trim(), order);
        Specification<Inspection> base = queueTarget(type, partCode, predictedQuality);

        // size+1건을 읽어 다음 페이지 유무 판단
        List<QueueRow> rows = order == QueueSort.PRIORITY
                ? priorityRows(base, after, size + 1)
                : fetchRows(base, null, after, size + 1);
        boolean hasNext = rows.size() > size;
        List<QueueRow> page = hasNext ? rows.subList(0, size) : rows;
        List<Inspection> inspections = page.stream().map(QueueRow::inspection).toList();
        Map<String, String> urls = thumbnails.urlsFor(inspections);
        List<QueueItem> items = inspections.stream().map(i -> new QueueItem(i.getId(), i.getInspectionNo(),
                i.getPart().getPartCode(), DisplayState.of(i), i.getPredictedQuality(), i.getReviewReason(),
                i.getCalibratedDefectProbability(), i.getPassThresholdApplied(),
                InspectionQueryService.errorCodeOf(i), Times.toOffset(i.getReceivedAt()), urls.get(i.getId()))).toList();
        QueueRow last = page.isEmpty() ? null : page.get(page.size() - 1);
        String nextCursor = hasNext
                ? new QueueCursor(last.group(), last.inspection().getReceivedAt(), last.inspection().getId()).encode()
                : null;
        return new QueueResponse(items, nextCursor);
    }

    private Specification<Inspection> queueTarget(QueueType type, String partCode, PredictedQuality predictedQuality) {
        Specification<Inspection> target = switch (type == null ? QueueType.ALL : type) {
            case REVIEW -> InspectionSpecs.reviewPending();
            case FAILED -> InspectionSpecs.failedNotRetried();
            case ALL -> InspectionSpecs.reviewPending().or(InspectionSpecs.failedNotRetried());
        };
        Specification<Inspection> spec = InspectionSpecs.fetchPart().and(target);
        if (partCode != null && !partCode.isBlank()) {
            Part part = partRepository.findByPartCode(partCode.trim())
                    .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_PART_CODE));
            spec = spec.and(InspectionSpecs.partId(part.getId()));
        }
        // 예측이 없는 FAILED·수동 판정은 예측 필터를 주면 나오지 않음
        return predictedQuality == null ? spec : spec.and(InspectionSpecs.predictedQuality(predictedQuality));
    }

    // 우선 그룹(0) → 나머지(1) 순서. 커서가 나머지 그룹이면 우선 그룹은 이미 다 읽은 것
    private List<QueueRow> priorityRows(Specification<Inspection> base, QueueCursor after, int limit) {
        List<QueueRow> rows = new ArrayList<>();
        int startGroup = after == null ? PRIORITY_GROUP : after.group();
        for (int group = startGroup; group <= REST_GROUP && rows.size() < limit; group++) {
            Specification<Inspection> spec = base.and(group == PRIORITY_GROUP
                    ? InspectionSpecs.priorityReview() : InspectionSpecs.notPriorityReview());
            QueueCursor groupAfter = after != null && after.group() == group ? after : null;
            rows.addAll(fetchRows(spec, group, groupAfter, limit - rows.size()));
        }
        return rows;
    }

    private List<QueueRow> fetchRows(Specification<Inspection> spec, Integer group, QueueCursor after, int limit) {
        Specification<Inspection> paged = after == null ? spec
                : spec.and(InspectionSpecs.after(after.receivedAt(), after.id()));
        return inspectionRepository.findBy(paged, q -> q.sortBy(QUEUE_SORT).limit(limit).all()).stream()
                .map(i -> new QueueRow(i, group)).toList();
    }

    private record QueueRow(Inspection inspection, Integer group) {
    }

    private static Map<String, Long> toMap(List<PartCount> counts) {
        return counts.stream().collect(Collectors.toMap(PartCount::partId, PartCount::count));
    }
}
