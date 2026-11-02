package com.capstone.inspection.part;

import com.capstone.inspection.ai.ModelAvailability;
import com.capstone.inspection.ai.ModelAvailabilityService;
import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.InspectionItemRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.part.dto.PartResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PartService {

    private final PartRepository partRepository;
    private final InspectionItemRepository itemRepository;
    private final AiModelRepository aiModelRepository;
    private final AutomationPolicyRepository policyRepository;
    private final ModelAvailabilityService modelAvailability;

    // 부품 → 검사항목 → 활성 모델 상태를 묶어서 반환
    public List<PartResponse> getParts() {
        List<Part> parts = partRepository.findAll(Sort.by("partCode"));

        // 부품 ID별 검사항목 목록
        Map<String, List<InspectionItem>> itemsByPartId = itemRepository.findAllWithPart().stream()
                .collect(Collectors.groupingBy(item -> item.getPart().getId()));

        // 검사항목 ID별 활성 모델 (항목당 1개가 원칙, 중복 시 첫 번째 사용)
        Map<String, AiModel> activeModelByItemId = aiModelRepository.findAllActiveWithItem().stream()
                .collect(Collectors.toMap(m -> m.getItem().getId(), Function.identity(), (a, b) -> a));

        // 활성 모델 중 로드 확인된 것, 활성 모델에 ready·active 정책이 있는 항목
        Set<String> availableModelIds = activeModelByItemId.values().stream()
                .filter(m -> modelAvailability.check(m.getModelVersion()) == ModelAvailability.AVAILABLE)
                .map(AiModel::getId).collect(Collectors.toSet());
        Set<String> itemsWithPolicy = Set.copyOf(policyRepository.findItemIdsWithActivePolicy());

        return parts.stream()
                .map(p -> PartResponse.of(p, itemsByPartId.getOrDefault(p.getId(), List.of()), activeModelByItemId,
                        availableModelIds, itemsWithPolicy))
                .toList();
    }
}
